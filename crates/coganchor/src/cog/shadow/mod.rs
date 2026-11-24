//! A lazily materialised mirror of the target's workspace. Port of `hmz.coganchor.shadow`.
//! [Unit 9]
//!
//! Instead of forwarding every `read` and `getdents64`, the cog reproduces the target's
//! structure here the first time a directory is touched: real directories, real symlinks, and
//! sparse placeholder files of the target's size, mode and mtime. From then on `stat`,
//! `getdents64`, `read`, `write`, `mmap` and `lseek` run natively and still tell the truth.
//! Only two things cross the network per file: its content, pulled the first time it is
//! opened for reading, and pushed when it was changed here and must be seen there (before any
//! remote command runs). A remote command may change anything, so finishing one bumps a
//! generation that invalidates every cached listing.
//!
//! Several turns may share one mirror, each a cog of its own, through the ledger beside the
//! mirror's registry entry (`<base>.journal` and `<base>.live`, `flock`ed), in the line format
//! `hmz.coganchor.shadow._Ledger` writes: see [`ledger`].
//!
//! Paths are kept as the wire spells them ([`crate::proto::json::from_os`]), the strings the
//! ledger records and Python's surrogate-escaped `str`s stand for.

mod ledger;
mod registry;
#[cfg(test)]
mod tests;

use std::collections::{BTreeSet, HashMap, HashSet};
use std::fs::{self, File};
use std::io::{self, Write};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, PoisonError};

use nix::fcntl::AT_FDCWD;
use nix::sys::stat::{UtimensatFlags, utimensat};
use nix::sys::time::TimeSpec;
use serde_json::{Value, json};

use crate::client::RemoteClient;
use crate::cog::router::{Place, Router};
use crate::proto::json::{from_os, to_os};
use crate::proto::{Meta, Op, RemoteError};

pub use registry::{FORMERLY, REGISTRY_DIR, SHADOWS, UNMIRRORED};

use ledger::Ledger;

/// What a fetch is written to beside its file before it is moved over it (`_FETCH_SUFFIX`).
pub const FETCH_SUFFIX: &str = ".humanize-fetch";

/// Bound on symlink chasing, matching the kernel's own `ELOOP` limit (`_MAX_LINK_HOPS`).
const MAX_LINK_HOPS: usize = 40;

/// The calls the tree makes of the target: [`RemoteClient`]'s, behind a trait a test fakes.
trait Remote: Send + Sync {
    /// `LISTDIR`: `{"entries": [{name, kind, mode, size, mtime_ns, target?}, ..], ..}`.
    fn listdir(&self, path: &str) -> Result<Meta, RemoteError>;
    /// A whole file and `{size, mode, mtime_ns}`.
    fn read_file(&self, path: &str) -> Result<(Vec<u8>, Meta), RemoteError>;
    /// Writes a whole file, returning its `stat`.
    fn write_file(&self, path: &str, data: &[u8], mode: Option<u32>) -> Result<Meta, RemoteError>;
}

impl Remote for RemoteClient {
    fn listdir(&self, path: &str) -> Result<Meta, RemoteError> {
        let mut request = Meta::new();
        request.insert("path".into(), Value::from(path));
        self.call(Op::Listdir, request)
    }

    fn read_file(&self, path: &str) -> Result<(Vec<u8>, Meta), RemoteError> {
        RemoteClient::read_file(self, path)
    }

    fn write_file(&self, path: &str, data: &[u8], mode: Option<u32>) -> Result<Meta, RemoteError> {
        RemoteClient::write_file(self, path, data, mode)
    }
}

/// Which paths are the target's, and as what: the part of [`Router`] the tree asks
/// (`layout_for` and `to_virtual` in Python).
trait Mapping: Send + Sync {
    /// The path the target knows the mirror path `local` by, or `None` for one that stays here.
    fn virtual_path(&self, local: &str) -> Option<String>;
}

impl Mapping for Router {
    fn virtual_path(&self, local: &str) -> Option<String> {
        match self.place(local) {
            Place::Mirror { virtual_path, .. } => Some(virtual_path),
            Place::Local => None,
        }
    }
}

/// What the tree last knew about one path, on both sides (`FileRecord`). Its fields, in this
/// order, are a ledger `file` entry's.
#[derive(Clone, Debug, PartialEq, Eq)]
struct FileRecord {
    /// `file`, `dir`, `link` or `other`, as the target listed it.
    kind: String,
    mode: u32,
    remote_size: i64,
    remote_mtime_ns: i64,
    /// Whether the bytes here are the file's (fetched, written, or empty), not a placeholder.
    content_present: bool,
    /// `(size, mtime_ns)` here when the tree last wrote it, or `-1`s.
    local_size: i64,
    local_mtime_ns: i64,
}

impl FileRecord {
    fn new(kind: &str, mode: u32, remote_size: i64, remote_mtime_ns: i64) -> FileRecord {
        FileRecord {
            kind: kind.to_owned(),
            mode,
            remote_size,
            remote_mtime_ns,
            content_present: false,
            local_size: -1,
            local_mtime_ns: -1,
        }
    }

    /// Whether the target still has what this records, by kind, size and mtime.
    fn matches_remote(&self, entry: &Listed) -> bool {
        self.kind == entry.kind
            && self.remote_size == entry.size
            && self.remote_mtime_ns == entry.mtime_ns
    }

    /// The record a ledger `file` entry's fields after the path make: `FileRecord(*rest)`,
    /// four to seven of them, the rest defaulted.
    fn from_fields(rest: &[Value]) -> Option<FileRecord> {
        if !(4..=7).contains(&rest.len()) {
            return None;
        }
        let int = |at: usize| match rest.get(at) {
            None => Some(-1),
            Some(value) => value.as_i64(),
        };
        Some(FileRecord {
            kind: rest[0].as_str()?.to_owned(),
            mode: u32::try_from(rest[1].as_u64()?).ok()?,
            remote_size: rest[2].as_i64()?,
            remote_mtime_ns: rest[3].as_i64()?,
            content_present: match rest.get(4) {
                None => false,
                Some(Value::Bool(said)) => *said,
                Some(other) => other.as_i64()? != 0,
            },
            local_size: int(5)?,
            local_mtime_ns: int(6)?,
        })
    }
}

/// One entry of a `LISTDIR` reply.
struct Listed {
    name: String,
    kind: String,
    mode: u32,
    size: i64,
    mtime_ns: i64,
    target: String,
}

impl Listed {
    fn parse(said: &Value) -> Option<Listed> {
        Some(Listed {
            name: said.get("name")?.as_str()?.to_owned(),
            kind: said.get("kind")?.as_str()?.to_owned(),
            mode: u32::try_from(said.get("mode")?.as_u64()?).ok()?,
            size: said.get("size")?.as_i64()?,
            mtime_ns: said.get("mtime_ns")?.as_i64()?,
            target: said
                .get("target")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned(),
        })
    }
}

/// What a tree knows, behind its lock.
struct State {
    /// The generation each directory was last listed in.
    dirs: HashMap<String, u64>,
    files: HashMap<String, FileRecord>,
    /// Paths that may have been written since last pushed; flushed in sorted order.
    dirty: BTreeSet<String>,
    generation: u64,
    /// Shared with the other turns in the mirror; `None` for a tree that keeps to itself.
    ledger: Option<Ledger>,
}

/// The mirror one turn works in.
pub struct ShadowTree {
    remote: Arc<dyn Remote>,
    mapping: Arc<dyn Mapping>,
    state: Mutex<State>,
}

impl ShadowTree {
    /// The mirror at `mirror`, joining its ledger. A ledger that cannot be opened is said and
    /// done without: the tree then keeps what it knows to itself.
    pub fn new(
        client: Arc<RemoteClient>,
        router: Arc<Router>,
        mirror: &Path,
    ) -> io::Result<ShadowTree> {
        let entry = registry::registry_entry(&registry::registry_dir(), mirror);
        Ok(ShadowTree::build(client, router, Some((&entry, mirror))))
    }

    /// A tree over any target and mapping; with `ledger`, sharing the ledger kept beside the
    /// registry entry given (`<entry>` less `.json`) for the mirror named.
    fn build(
        remote: Arc<dyn Remote>,
        mapping: Arc<dyn Mapping>,
        ledger: Option<(&Path, &Path)>,
    ) -> ShadowTree {
        let ledger = ledger.and_then(|(entry, mirror)| {
            let base = entry.with_extension("");
            Ledger::open(&base)
                .map_err(|why| {
                    tracing::warn!(
                        "{} cannot be shared with other turns working in it, which may then \
                         lose what this one writes: {why}",
                        mirror.display()
                    );
                })
                .ok()
        });
        ShadowTree {
            remote,
            mapping,
            state: Mutex::new(State {
                dirs: HashMap::new(),
                files: HashMap::new(),
                dirty: BTreeSet::new(),
                generation: 0,
                ledger,
            }),
        }
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, State> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Stops sharing what this tree knows, for the other turns in the mirror to go on alone.
    /// A tree not closed is let go of when dropped, or when its process ends.
    pub fn close(&self) {
        self.lock().ledger = None;
    }

    /// Makes the directories leading to `local` exist, listed from the target.
    pub fn ensure_path(&self, local: &Path) -> Result<(), RemoteError> {
        self.ensure_path_in(&mut self.lock(), &from_path(local))
    }

    /// Makes `local` a listed directory (removing it here where the target lacks it).
    pub fn ensure_directory(&self, local: &Path) -> Result<(), RemoteError> {
        self.ensure_directory_in(&mut self.lock(), &from_path(local))
    }

    /// Fetches `local`'s content if it is still a placeholder; a symlink's, that of the file
    /// it leads to. Not called for an open that truncates a file it only writes, which never
    /// needs the old bytes ([`ShadowTree::note_write`] then keeps them from being fetched over
    /// what is written).
    pub fn ensure_content(&self, local: &Path) -> Result<(), RemoteError> {
        let local = from_path(local);
        if self.mapping.virtual_path(&local).is_none() {
            return Ok(());
        }
        self.shared(&mut self.lock(), |s| self.fetch(s, &local))
    }

    /// Notes that `local` may be written, so the next flush compares and pushes it.
    pub fn note_write(&self, local: &Path) {
        let local = from_path(local);
        if self.mapping.virtual_path(&local).is_none() {
            return;
        }
        let noted = self.shared(&mut self.lock(), |s| {
            if s.dirty.insert(local.clone()) {
                tell(s, json!(["dirty", local]));
            }
            Ok(())
        });
        if let Err(why) = noted {
            tracing::warn!("{local} is noted as written by this turn alone: {why}");
        }
    }

    /// Notes that `local` (and everything under it) was removed on the target (`forget`).
    pub fn note_removed(&self, local: &Path) {
        let local = from_path(local);
        let noted = self.shared(&mut self.lock(), |s| {
            forget(s, &local);
            Ok(())
        });
        if let Err(why) = noted {
            tracing::warn!("{local} is noted as removed by this turn alone: {why}");
        }
    }

    /// Notes that `from` was renamed to `to` on the target, carrying what is known across
    /// (`rename`): a renamed placeholder that lost its record would read as zeroes.
    pub fn note_renamed(&self, from: &Path, to: &Path) {
        let (from, to) = (from_path(from), from_path(to));
        let noted = self.shared(&mut self.lock(), |s| {
            relocate(s, &from, &to);
            tell(s, json!(["rename", from, to]));
            Ok(())
        });
        if let Err(why) = noted {
            tracing::warn!("{from} is noted as renamed by this turn alone: {why}");
        }
    }

    /// Notes that `to` now names what `from` does, as a hard link does (`duplicate`): without
    /// a record of its own, a placeholder never fetched would read as zeroes through it.
    pub fn note_linked(&self, from: &Path, to: &Path) -> Result<(), RemoteError> {
        let (from, to) = (from_path(from), from_path(to));
        self.shared(&mut self.lock(), |s| {
            let Some(mut copy) = s.files.get(&from).cloned() else {
                return Ok(());
            };
            record_local_state(&to, &mut copy);
            keep(s, &to, copy);
            Ok(())
        })
    }

    /// Pushes every written file whose size or mtime changed.
    pub fn flush(&self) -> Result<(), RemoteError> {
        self.flush_counted().map(drop)
    }

    /// [`ShadowTree::flush`], returning how many files were pushed. Every turn working in the
    /// mirror is flushed for, whichever does it: a file another turn wrote is on the target
    /// before this one reads a directory holding it.
    pub fn flush_counted(&self) -> Result<usize, RemoteError> {
        self.shared(&mut self.lock(), |s| self.flush_in(s))
    }

    /// Forgets every cached listing (a remote command may have changed anything).
    pub fn invalidate(&self) {
        self.lock().generation += 1;
    }

    // ------------------------------------------------------------------ internals

    /// Runs `f` holding the mirror, having first caught up with the other turns (`_shared`).
    fn shared<R>(
        &self,
        s: &mut State,
        f: impl FnOnce(&mut State) -> Result<R, RemoteError>,
    ) -> Result<R, RemoteError> {
        let Some(ledger) = s.ledger.as_mut() else {
            return f(s);
        };
        let entries = ledger
            .enter()
            .map_err(|why| RemoteError::from_io(&why, None))?;
        for entry in entries {
            replay(s, entry);
        }
        // Let go of even when `f` panics, as Python's `finally` does: a journal left locked
        // stalls every other turn in the mirror for good.
        let done = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| f(&mut *s)));
        if let Some(ledger) = s.ledger.as_mut() {
            ledger.exit();
        }
        done.unwrap_or_else(|panic| std::panic::resume_unwind(panic))
    }

    fn ensure_path_in(&self, s: &mut State, local: &str) -> Result<(), RemoteError> {
        let parent = dirname(local.trim_end_matches('/'));
        self.ensure_directory_in(s, if parent.is_empty() { "/" } else { &parent })
    }

    /// Mirrors one remote directory here, at most once per generation.
    fn ensure_directory_in(&self, s: &mut State, local: &str) -> Result<(), RemoteError> {
        let Some(virtual_path) = self.mapping.virtual_path(local) else {
            return Ok(());
        };
        if s.dirs.get(local) == Some(&s.generation) {
            return Ok(());
        }
        self.shared(s, |s| {
            self.flush_in(s)?;
            match self.remote.listdir(&virtual_path) {
                Err(why) if [libc::ENOENT, libc::ENOTDIR, libc::EACCES].contains(&why.errno) => {
                    // As Python does, though the forgetting below drops it again: a directory
                    // the target lacks is asked after anew, which finds it once it is made.
                    s.dirs.insert(local.to_owned(), s.generation);
                    // Gone on the target: so here too, and forgotten, listing and all.
                    if is_real_dir(local) {
                        remove_any(local);
                    }
                    forget(s, local);
                    Ok(())
                }
                Err(why) => Err(why),
                Ok(listing) => {
                    self.apply_listing(s, local, &listing)?;
                    s.dirs.insert(local.to_owned(), s.generation);
                    Ok(())
                }
            }
        })
    }

    fn fetch(&self, s: &mut State, local: &str) -> Result<(), RemoteError> {
        self.ensure_path_in(s, local)?;
        // Opening a symlink reads whatever it points at: that is the file to have here.
        let path = self.follow_links(s, local)?;
        let Some(virtual_path) = self.mapping.virtual_path(&path) else {
            return Ok(());
        };
        let Some(mut record) = s.files.get(&path).cloned() else {
            return Ok(());
        };
        // Here already, or written over since: newer than what the target has to give.
        if record.kind != "file" || record.content_present || unpushed(s, &path) {
            return Ok(());
        }
        let (data, meta) = self.remote.read_file(&virtual_path)?;
        let scratch = format!("{path}{FETCH_SUFFIX}");
        let placed = (|| {
            File::create(os(&scratch))?.write_all(&data)?;
            fs::set_permissions(
                os(&scratch),
                fs::Permissions::from_mode(record.mode & 0o7777),
            )?;
            fs::rename(os(&scratch), os(&path))
        })();
        if let Err(why) = placed {
            let _ = fs::remove_file(os(&scratch));
            return Err(local_error(&why, &path));
        }
        let size = meta_i64(&meta, "size").unwrap_or(data.len() as i64);
        let mtime_ns = meta_i64(&meta, "mtime_ns").unwrap_or(record.remote_mtime_ns);
        set_mtime(&path, mtime_ns).map_err(|why| local_error(&why, &path))?;
        record.remote_size = size;
        record.remote_mtime_ns = mtime_ns;
        record.content_present = true;
        record_local_state(&path, &mut record);
        keep(s, &path, record);
        Ok(())
    }

    /// Resolves symlinks here, materialising each directory on the way (`_follow_links`).
    fn follow_links(&self, s: &mut State, local: &str) -> Result<String, RemoteError> {
        let mut path = local.to_owned();
        for _ in 0..MAX_LINK_HOPS {
            let Ok(target) = fs::read_link(os(&path)) else {
                return Ok(path);
            };
            path = normpath(&join(&dirname(&path), &from_path(&target)));
            if self.mapping.virtual_path(&path).is_none() {
                return Ok(path);
            }
            self.ensure_path_in(s, &path)?;
        }
        Ok(path)
    }

    fn flush_in(&self, s: &mut State) -> Result<usize, RemoteError> {
        let mut pushed = 0;
        for local in s.dirty.clone() {
            let Some(virtual_path) = self.mapping.virtual_path(&local) else {
                continue;
            };
            // Gone here: the unlink was replayed already.
            let Ok(info) = fs::symlink_metadata(os(&local)) else {
                continue;
            };
            if !info.file_type().is_file() {
                continue;
            }
            if s.files.get(&local).is_some_and(|record| {
                record.local_size == info.size() as i64 && record.local_mtime_ns == mtime_ns(&info)
            }) {
                continue;
            }
            self.push(s, &local, &virtual_path, &info)?;
            pushed += 1;
        }
        Ok(pushed)
    }

    fn push(
        &self,
        s: &mut State,
        local: &str,
        virtual_path: &str,
        info: &fs::Metadata,
    ) -> Result<(), RemoteError> {
        let data = fs::read(os(local)).map_err(|why| local_error(&why, local))?;
        let meta = self
            .remote
            .write_file(virtual_path, &data, Some(info.mode()))?;
        // As it was before it was read: a write landing while it was being sent is one the
        // next flush sees, not one taken for what went.
        let record = FileRecord {
            kind: "file".into(),
            mode: info.mode(),
            remote_size: meta_i64(&meta, "size").unwrap_or(info.size() as i64),
            remote_mtime_ns: meta_i64(&meta, "mtime_ns").unwrap_or(0),
            content_present: true,
            local_size: info.size() as i64,
            local_mtime_ns: mtime_ns(info),
        };
        keep(s, local, record);
        tracing::debug!("pushed {local} -> {virtual_path} ({} bytes)", info.size());
        Ok(())
    }

    fn apply_listing(&self, s: &mut State, local: &str, listing: &Meta) -> Result<(), RemoteError> {
        fs::create_dir_all(os(local)).map_err(|why| local_error(&why, local))?;
        let malformed = || RemoteError::new(libc::EPROTO, "a listing the anchor sent is malformed");
        let entries = listing
            .get("entries")
            .and_then(Value::as_array)
            .ok_or_else(malformed)?;
        let mut expected = HashSet::new();
        for said in entries {
            let entry = Listed::parse(said).ok_or_else(malformed)?;
            let path = join(local, &entry.name);
            self.apply_entry(s, &path, &entry)
                .map_err(|why| local_error(&why, &path))?;
            expected.insert(entry.name);
        }
        self.remove_vanished(s, local, &expected);
        Ok(())
    }

    fn apply_entry(&self, s: &mut State, path: &str, entry: &Listed) -> io::Result<()> {
        if unpushed(s, path) {
            return Ok(()); // the next flush carries it there, over whatever the target has
        }
        match entry.kind.as_str() {
            "dir" => {
                if fs::symlink_metadata(os(path)).is_ok_and(|info| !info.is_dir()) {
                    remove_any(path);
                }
                fs::create_dir_all(os(path))?;
                let mut record = FileRecord::new("dir", entry.mode, entry.size, entry.mtime_ns);
                record.content_present = true;
                if s.files.get(path) != Some(&record) {
                    keep(s, path, record);
                }
            }
            "link" => {
                if fs::read_link(os(path)).is_ok_and(|was| from_path(&was) == entry.target) {
                    return Ok(());
                }
                remove_any(path);
                std::os::unix::fs::symlink(os(&entry.target), os(path))?;
                let mut record = FileRecord::new("link", entry.mode, entry.size, entry.mtime_ns);
                record.content_present = true;
                keep(s, path, record);
            }
            _ => self.apply_file(s, path, entry)?,
        }
        Ok(())
    }

    /// A sparse placeholder of the target's size, mode and mtime, which makes `stat`,
    /// `getdents64` and `ls` here report the target's truth for free (`_apply_file`).
    fn apply_file(&self, s: &mut State, path: &str, entry: &Listed) -> io::Result<()> {
        if s.files
            .get(path)
            .is_some_and(|record| record.matches_remote(entry) && is_intact(path, record))
        {
            return Ok(());
        }
        // Python opens through a symlink here, truncating whatever it leads to; the link is
        // what the target replaced, so it is removed instead.
        // Whatever is there goes, a placeholder included: one the target made read-only
        // cannot be opened to be truncated again (Python's `open(path, "wb")` fails so).
        if fs::symlink_metadata(os(path)).is_ok() {
            remove_any(path);
        }
        let mut fresh = FileRecord::new(&entry.kind, entry.mode, entry.size, entry.mtime_ns);
        fresh.content_present = entry.size == 0 && entry.kind == "file";
        let placeholder = File::create(os(path))?;
        if entry.size > 0 && entry.kind == "file" {
            placeholder.set_len(entry.size as u64)?;
        }
        drop(placeholder);
        fs::set_permissions(os(path), fs::Permissions::from_mode(entry.mode & 0o7777))?;
        set_mtime(path, entry.mtime_ns)?;
        record_local_state(path, &mut fresh);
        keep(s, path, fresh);
        Ok(())
    }

    /// Removes what the target no longer lists (`_remove_vanished`). Scratch from an
    /// interrupted fetch goes too: nothing else removes it, and no fetch can be in flight,
    /// both running holding the mirror, whichever turn runs them.
    fn remove_vanished(&self, s: &mut State, local: &str, expected: &HashSet<String>) {
        let Ok(listing) = fs::read_dir(os(local)) else {
            return;
        };
        let present: Vec<String> = listing
            .filter_map(Result::ok)
            .map(|one| from_os(&one.file_name()))
            .collect();
        for name in present {
            if expected.contains(&name) {
                continue;
            }
            let path = join(local, &name);
            if unpushed(s, &path) {
                continue; // made since the flush before this listing: the next one sends it
            }
            self.note_unforwarded(s, &path);
            remove_any(&path);
            forget(s, &path);
        }
    }

    /// Says out loud when what is about to be dropped was never carried across
    /// (`_note_unforwarded`). The mirror is authoritative, so what the target lacks is
    /// deleted: right for a file the target removed, silent loss for one written here without
    /// passing a handler, as through a path the routing did not recognise. The two are told
    /// apart by the record a file mirrored from the target has.
    fn note_unforwarded(&self, s: &State, path: &str) {
        let virtual_path = self.mapping.virtual_path(path);
        let regular = fs::symlink_metadata(os(path)).is_ok_and(|info| info.file_type().is_file());
        match virtual_path {
            Some(virtual_path)
                if !s.files.contains_key(path) && !path.ends_with(FETCH_SUFFIX) && regular =>
            {
                tracing::warn!(
                    "{path} was written here but never reached the target as {virtual_path}, \
                     and is being dropped; the agent may have been told it succeeded"
                );
            }
            _ => tracing::debug!("dropping {path}: gone on the target"),
        }
    }
}

/// Whether a file here was written since last pushed, by any turn in the mirror (`_unpushed`):
/// newer than anything the target says of it.
fn unpushed(s: &State, path: &str) -> bool {
    if !s.dirty.contains(path) {
        return false;
    }
    let Ok(info) = fs::symlink_metadata(os(path)) else {
        return false;
    };
    if !info.file_type().is_file() {
        return false;
    }
    s.files.get(path).is_none_or(|record| {
        (record.local_size, record.local_mtime_ns) != (info.size() as i64, mtime_ns(&info))
    })
}

/// Records `record` for `path`, and tells the other turns (`_keep`).
fn keep(s: &mut State, path: &str, record: FileRecord) {
    let entry = json!([
        "file",
        path,
        record.kind,
        record.mode,
        record.remote_size,
        record.remote_mtime_ns,
        record.content_present,
        record.local_size,
        record.local_mtime_ns,
    ]);
    s.files.insert(path.to_owned(), record);
    tell(s, entry);
}

fn tell(s: &mut State, entry: Value) {
    if let Some(ledger) = s.ledger.as_mut() {
        ledger.tell(&entry);
    }
}

/// Drops what is known of `path`'s subtree, and tells the other turns (`forget`).
fn forget(s: &mut State, path: &str) {
    drop_subtree(s, path);
    tell(s, json!(["forget", path]));
}

/// Applies one change another turn made to what it knows (`_replay`); one not understood is
/// passed over, as Python passes over one it cannot unpack.
fn replay(s: &mut State, entry: Value) {
    let understood = (|| {
        let items = entry.as_array()?;
        let what = items.first()?.as_str()?;
        let path = items.get(1)?.as_str()?;
        match what {
            "file" => {
                let record = FileRecord::from_fields(&items[2..])?;
                s.files.insert(path.to_owned(), record);
            }
            "dirty" => {
                s.dirty.insert(path.to_owned());
            }
            "forget" => drop_subtree(s, path),
            "rename" if items.len() == 3 => relocate(s, path, items[2].as_str()?),
            "rename" => return None,
            _ => {}
        }
        Some(())
    })();
    if understood.is_none() {
        tracing::debug!("ignoring a journal entry {entry}");
    }
}

/// Whether `path` is `root` or beneath it (`_subtree_test`); a `root` spelled with trailing
/// slashes names the same directory as one without.
fn covers(root: &str, path: &str) -> bool {
    let stem = root.trim_end_matches('/');
    path == root
        || path == stem
        || path
            .strip_prefix(stem)
            .is_some_and(|rest| rest.starts_with('/'))
}

fn drop_subtree(s: &mut State, root: &str) {
    s.files.retain(|key, _| !covers(root, key));
    s.dirs.retain(|key, _| !covers(root, key));
    s.dirty.retain(|key| !covers(root, key));
}

/// Moves what is known from under `from` to the same place under `to` (`_move`).
fn relocate(s: &mut State, from: &str, to: &str) {
    drop_subtree(s, to);
    // Python slices `len(source)` off; here the part past `from` is cut where `covers`
    // matched it, so a `from` spelled with a trailing slash keeps the separator.
    let stem = from.trim_end_matches('/');
    let rebase = |key: String| {
        if key == from || key == stem {
            to.to_owned()
        } else if covers(from, &key) {
            format!("{}{}", to.trim_end_matches('/'), &key[stem.len()..])
        } else {
            key
        }
    };
    s.files = std::mem::take(&mut s.files)
        .into_iter()
        .map(|(key, value)| (rebase(key), value))
        .collect();
    s.dirs = std::mem::take(&mut s.dirs)
        .into_iter()
        .map(|(key, value)| (rebase(key), value))
        .collect();
    s.dirty = std::mem::take(&mut s.dirty)
        .into_iter()
        .map(rebase)
        .collect();
}

/// Records `(size, mtime_ns)` as `path` has them now (`_record_local_state`).
fn record_local_state(path: &str, record: &mut FileRecord) {
    if let Ok(info) = fs::symlink_metadata(os(path)) {
        record.local_size = info.size() as i64;
        record.local_mtime_ns = mtime_ns(&info);
    }
}

/// Whether `path` still is as the tree last made it (`_is_intact`).
fn is_intact(path: &str, record: &FileRecord) -> bool {
    fs::symlink_metadata(os(path)).is_ok_and(|info| {
        info.size() as i64 == record.local_size && mtime_ns(&info) == record.local_mtime_ns
    })
}

fn is_real_dir(path: &str) -> bool {
    fs::symlink_metadata(os(path)).is_ok_and(|info| info.is_dir())
}

/// Removes a file, link or whole directory, saying (at debug) what could not be.
fn remove_any(path: &str) {
    let removed = if is_real_dir(path) {
        fs::remove_dir_all(os(path))
    } else {
        fs::remove_file(os(path))
    };
    if let Err(why) = removed {
        tracing::debug!("could not remove {path}: {why}");
    }
}

/// Sets atime and mtime both to `mtime_ns`, to the nanosecond.
fn set_mtime(path: &str, mtime_ns: i64) -> io::Result<()> {
    let at = TimeSpec::new(
        mtime_ns.div_euclid(1_000_000_000) as _,
        mtime_ns.rem_euclid(1_000_000_000) as _,
    );
    utimensat(AT_FDCWD, &os(path), &at, &at, UtimensatFlags::FollowSymlink)?;
    Ok(())
}

fn mtime_ns(info: &fs::Metadata) -> i64 {
    info.mtime() * 1_000_000_000 + info.mtime_nsec()
}

fn meta_i64(meta: &Meta, key: &str) -> Option<i64> {
    meta.get(key).and_then(Value::as_i64)
}

/// A failure here, as the error the tree's callers carry.
fn local_error(why: &io::Error, path: &str) -> RemoteError {
    RemoteError::from_io(why, Some(path))
}

/// A wire string as the path it names here.
fn os(path: &str) -> PathBuf {
    PathBuf::from(to_os(path))
}

/// A path as the wire spells it.
fn from_path(path: &Path) -> String {
    from_os(path.as_os_str())
}

/// `os.path.dirname`: everything before the last `/`, less trailing slashes unless that is all.
fn dirname(path: &str) -> String {
    let head = &path[..path.rfind('/').map_or(0, |at| at + 1)];
    let trimmed = head.trim_end_matches('/');
    if trimmed.is_empty() { head } else { trimmed }.to_owned()
}

/// `os.path.join` of two parts.
fn join(head: &str, tail: &str) -> String {
    if tail.starts_with('/') || head.is_empty() {
        tail.to_owned()
    } else if head.ends_with('/') {
        format!("{head}{tail}")
    } else {
        format!("{head}/{tail}")
    }
}

/// `os.path.normpath` (POSIX): `.`, `..` and repeated slashes resolved lexically.
fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".into();
    }
    // POSIX lets exactly two leading slashes mean something else, so Python keeps them.
    let leading = match path.len() - path.trim_start_matches('/').len() {
        0 => "",
        2 => "//",
        _ => "/",
    };
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            ".." if parts.last().is_some_and(|last| *last != "..") => {
                parts.pop();
            }
            ".." if !leading.is_empty() => {}
            part => parts.push(part),
        }
    }
    let joined = format!("{leading}{}", parts.join("/"));
    if joined.is_empty() {
        ".".into()
    } else {
        joined
    }
}

/// Guards and records a mirror directory: refuses one holding files that was never a mirror,
/// or was one of another target, unless `force` (protocol/core.md 6.6.5), with the kind
/// [`io::ErrorKind::AlreadyExists`] (Python's `FileExistsError`). A mirror path that is not a
/// directory, or cannot be made or recorded, is refused with a message beginning
/// [`UNMIRRORED`]. Records live in `$HUMANIZE_SHADOWS`, else `$XDG_STATE_HOME/humanize/shadows`,
/// else [`REGISTRY_DIR`].
pub fn prepare_shadow_root(root: &Path, force: bool, target: &str) -> io::Result<()> {
    registry::prepare_in(&registry::registry_dir(), root, force, target)
}
