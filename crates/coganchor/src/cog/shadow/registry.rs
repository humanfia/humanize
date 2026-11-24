//! Where mirrors are recorded, and the guard on taking a directory for one. Port of
//! `prepare_shadow_root`, `_recorded_target` and `_registry_entry` in `hmz.coganchor.shadow`.
//!
//! Mirrors are recorded outside themselves, so a mirror stays byte for byte what the target
//! has: an agent listing the workspace must not see the anchor's own bookkeeping. Each record
//! is `<registry>/<sha256(abspath(mirror))[:16]>.json`, holding `{"shadow": .., "target": ..}`;
//! the mirror's ledger is kept beside it (see [`super::ledger`]).

use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde_json::Value;
use sha2::{Digest, Sha256};

use super::ledger::python_json;
use super::{from_path, normpath};
use crate::proto::json::{self, to_os};

/// Where mirrors are recorded when nothing says otherwise: Humanize's own state, under
/// `$XDG_STATE_HOME` where that is an absolute path and here where it is not.
pub const REGISTRY_DIR: &str = "~/.local/state/humanize/shadows";

/// Where releases before recorded them, under the cache: moved to the registry the first time
/// it is asked for (see [`settle`]).
pub const FORMERLY: &str = "~/.cache/humanize/shadows";

/// What points the registry somewhere else, for one process and everything it starts: for a
/// machine that keeps its caches elsewhere, and for a test suite (`SHADOWS`).
pub const SHADOWS: &str = "HUMANIZE_SHADOWS";

/// The words protocol/core.md 6.6.5.2 has a mirror that cannot be kept refused with
/// (`UNMIRRORED` in `hmz.coganchor.anchor`, whose caller added them in Python).
pub const UNMIRRORED: &str = "cannot keep the local copy of the work at";

/// The registry directory: `$HUMANIZE_SHADOWS`, else `$XDG_STATE_HOME/humanize/shadows`, else
/// [`REGISTRY_DIR`], `~` expanded. Only the last two take over a registry kept at [`FORMERLY`]:
/// one the variable names is wherever it was put.
pub(super) fn registry_dir() -> PathBuf {
    if let Some(said) = std::env::var_os(SHADOWS).filter(|said| !said.is_empty()) {
        return expand_user(&said);
    }
    // A relative value is ignored, as the XDG specification has it.
    let at = match std::env::var_os("XDG_STATE_HOME").filter(|said| Path::new(said).is_absolute()) {
        Some(state) => Path::new(&state).join("humanize/shadows"),
        None => expand_user(REGISTRY_DIR.as_ref()),
    };
    settle(&expand_user(FORMERLY.as_ref()), &at);
    at
}

/// Moves a registry kept at `was` to `now`, once a process, where `now` is not there: one that
/// is holds what this release has recorded since, and the two are never merged. A rename, and
/// across devices a copy made beside `now` and renamed to it once it is whole, so that `now` is
/// never seen half there; then the original removed. Never fails: a registry anything else
/// refuses to move is left where it is, and a new one begun.
pub(super) fn settle(was: &Path, now: &Path) {
    static SETTLED: Mutex<Vec<(PathBuf, PathBuf)>> = Mutex::new(Vec::new());
    {
        let mut settled = SETTLED
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let pair = (was.to_path_buf(), now.to_path_buf());
        if settled.contains(&pair) {
            return;
        }
        settled.push(pair);
    }
    if fs::symlink_metadata(now).is_ok() || fs::symlink_metadata(was).is_err() {
        return;
    }
    if let Some(parent) = now.parent() {
        let _ = fs::create_dir_all(parent);
    }
    // Atomic, and refused where another process has meanwhile made `now` and put something in it.
    match fs::rename(was, now) {
        Err(why) if why.raw_os_error() == Some(libc::EXDEV) => {}
        _ => return,
    }
    let name = now.file_name().unwrap_or_default().to_string_lossy();
    let staged = now.with_file_name(format!(".{name}.{}", std::process::id()));
    if crate::cog::homes::copytree(was, &staged)
        .and_then(|()| fs::rename(&staged, now))
        .is_err()
    {
        let _ = fs::remove_dir_all(&staged);
        return;
    }
    let _ = fs::remove_dir_all(was);
}

/// The record of the mirror at `mirror` in `registry` (`_registry_entry`). The digest is of
/// the absolute, normalised path's bytes, which for a UTF-8 path is what Python hashes.
pub(super) fn registry_entry(registry: &Path, mirror: &Path) -> PathBuf {
    let digest = Sha256::digest(abspath(mirror).as_os_str().as_bytes());
    registry.join(format!("{}.json", &hex::encode(digest)[..16]))
}

/// Guards and records a mirror directory against `registry` (`prepare_shadow_root`).
pub(super) fn prepare_in(
    registry: &Path,
    root: &Path,
    force: bool,
    target: &str,
) -> io::Result<()> {
    let record = registry_entry(registry, root);
    let shown = root.display();
    let previous = recorded_target(&record);
    if let Some(previous) = &previous
        && previous != target
        && !force
    {
        return Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            format!(
                "{shown} mirrors {previous}, not {target}. Humanize replaces this directory \
                 with the new target's contents and would delete everything only the old one \
                 has. Use a different directory, or pass --force."
            ),
        ));
    }
    let unkept = |why: &io::Error| {
        // Not `AlreadyExists`: that kind says "another directory, or --force" to a caller.
        let kind = match why.kind() {
            io::ErrorKind::AlreadyExists => io::ErrorKind::Other,
            kind => kind,
        };
        io::Error::new(kind, format!("{UNMIRRORED} {shown}: {}", strerror(why)))
    };
    match fs::metadata(root) {
        Err(_) => fs::create_dir_all(root).map_err(|why| unkept(&why))?,
        Ok(info) if !info.is_dir() => {
            return Err(io::Error::new(
                io::ErrorKind::NotADirectory,
                format!("{UNMIRRORED} {shown}: shadow root is not a directory"),
            ));
        }
        Ok(_) => {
            if !force && previous.is_none() {
                let mut listing = fs::read_dir(root).map_err(|why| unkept(&why))?;
                if listing.next().is_some() {
                    return Err(io::Error::new(
                        io::ErrorKind::AlreadyExists,
                        format!(
                            "{shown} already contains files and is not a Humanize mirror. \
                             Humanize replaces this directory with the target's contents and \
                             would delete them. Use an empty directory, or pass --force."
                        ),
                    ));
                }
            }
        }
    }
    if let Some(parent) = record.parent() {
        fs::create_dir_all(parent).map_err(|why| unkept(&why))?;
    }
    // `json.dumps({"shadow": path, "target": target})`, default separators and all.
    let said = format!(
        "{{\"shadow\": {}, \"target\": {}}}",
        String::from_utf8(python_json(&Value::String(from_path(root)))).unwrap(),
        String::from_utf8(python_json(&Value::String(target.to_owned()))).unwrap(),
    );
    // Whole or not at all: a turn starting in this mirror reads it while another is writing
    // it, and half a record is none -- a mirror refused as somebody else's directory.
    write_atomically(&record, said.as_bytes()).map_err(|why| unkept(&why))
}

/// The target the mirror was last used against, or `None` for one never recorded or whose
/// record cannot be read (`_recorded_target`).
fn recorded_target(record: &Path) -> Option<String> {
    let blob = fs::read(record).ok()?;
    let value = json::decode(&blob).ok()?;
    Some(match value.as_object()?.get("target") {
        None => String::new(),
        Some(Value::String(said)) => said.clone(),
        // `str()` of what `json.load` makes of the rest, so both sides compare one spelling.
        Some(Value::Null) => "None".into(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Bool(false)) => "False".into(),
        Some(other) => other.to_string(),
    })
}

/// Replaces `at` with `said`, written beside it under a name of its own and moved over it,
/// keeping the mode it had (`atomic.writes`).
fn write_atomically(at: &Path, said: &[u8]) -> io::Result<()> {
    let keeps = fs::metadata(at)
        .ok()
        .map(|info| info.permissions().mode() & 0o7777);
    let name = at.file_name().unwrap_or_default().to_string_lossy();
    let (beside, mut file) = loop {
        let beside = at.with_file_name(format!(".{name}.{:016x}.new", rand::random::<u64>()));
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(if keeps.is_some() { 0o600 } else { 0o666 })
            .open(&beside)
        {
            Ok(file) => break (beside, file),
            Err(why) if why.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(why) => return Err(why),
        }
    };
    let written = (|| {
        if let Some(mode) = keeps {
            file.set_permissions(fs::Permissions::from_mode(mode))?;
        }
        file.write_all(said)?;
        file.sync_all()?;
        fs::rename(&beside, at)
    })();
    if written.is_err() {
        let _ = fs::remove_file(&beside);
    }
    written
}

/// `os.path.abspath`: joined to the working directory if relative, then normalised.
fn abspath(path: &Path) -> PathBuf {
    let joined = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_default().join(path)
    };
    PathBuf::from(to_os(&normpath(&from_path(&joined))))
}

/// `os.path.expanduser` of a leading `~` or `~/`: `$HOME`, else the password database's.
fn expand_user(said: &std::ffi::OsStr) -> PathBuf {
    let bytes = said.as_bytes();
    if bytes != b"~" && !bytes.starts_with(b"~/") {
        return PathBuf::from(said);
    }
    // An empty `$HOME` is taken as it is, as Python takes it: a Python turn and a Rust one
    // must find one registry, and so one ledger.
    let home = std::env::var_os("HOME").or_else(|| {
        nix::unistd::User::from_uid(nix::unistd::getuid())
            .ok()
            .flatten()
            .map(|user| user.dir.into_os_string())
    });
    let Some(home) = home else {
        return PathBuf::from(said);
    };
    let mut joined = home.into_vec();
    while joined.ends_with(b"/") {
        joined.pop();
    }
    joined.extend_from_slice(&bytes[1..]);
    if joined.is_empty() {
        joined.push(b'/');
    }
    PathBuf::from(OsString::from_vec(joined))
}

/// The error's message without Rust's ` (os error N)`, as Python's `strerror` reads.
fn strerror(why: &io::Error) -> String {
    let full = why.to_string();
    match full.rfind(" (os error ") {
        Some(cut) => full[..cut].to_owned(),
        None => full,
    }
}
