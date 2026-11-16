//! What every turn working in one mirror knows about it, kept beside its registry entry.
//! Port of `_Ledger` in `hmz.coganchor.shadow`, byte for byte: a Python turn and a Rust turn
//! may share one mirror, so each reads the journal lines the other writes.
//!
//! Each turn is a process of its own, and a tree that knows only what its own turn did takes
//! the others' work for something to put right: a file another turn wrote and has not pushed
//! is one the target lacks, and is swept away; one it pushed or fetched has no record here,
//! and is made a placeholder again. So what a tree changes in what it knows is appended to
//! `<base>.journal`, and what the others changed is read from it, under an exclusive `flock`
//! held for as long as the mirror is changed. A journal nobody else is reading is begun again,
//! which a shared `flock` on `<base>.live`, held for the life of the turn, tells.

use std::fs::File;
use std::io::{self, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::FileExt;
use std::path::{Path, PathBuf};

use nix::fcntl::OFlag;
use nix::sys::stat::Mode;
use serde_json::Value;

use crate::proto::json;

/// The two files and what this turn has read of, and has yet to add to, the journal.
pub(super) struct Ledger {
    journal: File,
    /// Only ever locked: its lock is what says a turn is in the mirror.
    live: File,
    /// How far into the journal this turn has read (and written).
    seen: u64,
    /// How many [`Ledger::enter`]s are open: the lock is taken by the first, let go by the last.
    depth: u32,
    /// Entries told since the lock was taken, each one compact JSON line.
    told: Vec<Vec<u8>>,
}

impl Ledger {
    /// Opens (making them) `<base>.journal` and `<base>.live`, and joins the mirror: a turn
    /// alone in it empties the journal first (`_Ledger.__init__`).
    pub(super) fn open(base: &Path) -> io::Result<Ledger> {
        if let Some(parent) = base.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let journal = open_raw(
            &suffixed(base, ".journal"),
            OFlag::O_RDWR | OFlag::O_APPEND | OFlag::O_CREAT,
        )?;
        // Opened read-only, as Python does: `OpenOptions` refuses to create a file so.
        let live = open_raw(&suffixed(base, ".live"), OFlag::O_RDONLY | OFlag::O_CREAT)?;
        flock(&journal, libc::LOCK_EX)?;
        let joined = (|| {
            match flock(&live, libc::LOCK_EX | libc::LOCK_NB) {
                Ok(()) => journal.set_len(0)?,
                // Another turn is here: what it knows is where this one starts.
                Err(error) if error.raw_os_error() == Some(libc::EWOULDBLOCK) => {}
                Err(error) => return Err(error),
            }
            flock(&live, libc::LOCK_SH)
        })();
        let _ = flock(&journal, libc::LOCK_UN);
        joined?;
        Ok(Ledger {
            journal,
            live,
            seen: 0,
            depth: 0,
            told: Vec::new(),
        })
    }

    /// Takes the mirror, re-entrantly; the outermost call locks the journal and returns every
    /// entry the other turns appended since this one last looked, for the caller to replay
    /// (`held`'s entry and `_catch_up`).
    pub(super) fn enter(&mut self) -> io::Result<Vec<Value>> {
        if self.depth > 0 {
            self.depth += 1;
            return Ok(Vec::new());
        }
        flock(&self.journal, libc::LOCK_EX)?;
        match self.catch_up() {
            Ok(entries) => {
                self.depth = 1;
                Ok(entries)
            }
            Err(error) => {
                let _ = flock(&self.journal, libc::LOCK_UN);
                Err(error)
            }
        }
    }

    /// Lets go of what [`Ledger::enter`] took; the outermost call appends what was told and
    /// unlocks the journal (`held`'s exit and `_write_out`).
    pub(super) fn exit(&mut self) {
        self.depth = self.depth.saturating_sub(1);
        if self.depth == 0 {
            self.write_out();
            let _ = flock(&self.journal, libc::LOCK_UN);
        }
    }

    /// Records one change, for the others to read once the mirror is let go of: one line of
    /// JSON spelled exactly as `json.dumps(entry, separators=(",", ":"))` spells it.
    pub(super) fn tell(&mut self, entry: &Value) {
        self.told.push(python_json(entry));
    }

    fn catch_up(&mut self) -> io::Result<Vec<Value>> {
        let end = self.journal.metadata()?.len();
        let mut blob = Vec::new();
        while self.seen < end {
            let mut chunk = vec![0; (end - self.seen) as usize];
            let read = self.journal.read_at(&mut chunk, self.seen)?;
            if read == 0 {
                break;
            }
            blob.extend_from_slice(&chunk[..read]);
            self.seen += read as u64;
        }
        // `bytes.splitlines` splits at `\n`, `\r` and `\r\n`; JSON escapes both inside strings.
        Ok(blob
            .split(|&b| b == b'\n' || b == b'\r')
            .filter(|line| !line.is_empty())
            // Half a line, from a turn killed while writing it, is passed over.
            .filter_map(|line| json::decode(line).ok())
            .collect())
    }

    fn write_out(&mut self) {
        if self.told.is_empty() {
            return;
        }
        // Begun on a line of its own, so that half of one a killed turn left is only that;
        // and one write, so that a turn reading it never finds only some of them.
        let mut blob = vec![b'\n'];
        blob.extend_from_slice(&self.told.join(&b'\n'));
        blob.push(b'\n');
        self.told.clear();
        if let Err(why) = (&self.journal).write_all(&blob) {
            tracing::warn!("the other turns in this mirror will not hear of a change: {why}");
        }
        if let Ok(info) = self.journal.metadata() {
            self.seen = info.len();
        }
    }
}

/// `base` with `suffix` appended to its last component.
fn suffixed(base: &Path, suffix: &str) -> PathBuf {
    let mut name = base.as_os_str().to_os_string();
    name.push(suffix);
    PathBuf::from(name)
}

/// `open(2)` with these flags and mode `0600`, as `os.open` makes them.
fn open_raw(path: &Path, flags: OFlag) -> io::Result<File> {
    let fd = nix::fcntl::open(
        path,
        flags | OFlag::O_CLOEXEC,
        Mode::from_bits_truncate(0o600),
    )?;
    Ok(File::from(fd))
}

/// `flock(2)`, retried when a signal interrupts it. Not `nix`'s: its free function is
/// deprecated, and its owning `Flock` cannot lock and unlock, again and again, a descriptor
/// held for the life of the turn, as the journal's is.
fn flock(file: &File, operation: libc::c_int) -> io::Result<()> {
    loop {
        // SAFETY: the descriptor is open for as long as `file` is borrowed.
        if unsafe { libc::flock(file.as_raw_fd(), operation) } == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error);
        }
    }
}

/// A value as Python's `json.dumps` writes it with `ensure_ascii` (its default): every
/// character past `~` escaped as `\uXXXX` in lowercase hex, those past the BMP as a surrogate
/// pair, and a byte stood in for (see [`json`]) as the lone `\udcXX` Python reads back as it.
/// Compact, as `separators=(",", ":")` and `serde_json` both write it.
pub(super) fn python_json(value: &Value) -> Vec<u8> {
    let text = String::from_utf8(json::encode(value)).expect("encode writes UTF-8");
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if (c as u32) < 0x7f {
            out.push(c);
        } else {
            let mut units = [0u16; 2];
            for unit in c.encode_utf16(&mut units) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    out.into_bytes()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::json::from_os;
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;

    #[test]
    fn spelled_as_python_spells_it() {
        let path = from_os(OsStr::from_bytes(
            b"/w/\xff/\xc3\xb6/\xf0\x9f\x98\x80\x7f\n\"",
        ));
        let entry = serde_json::json!(["file", path, "file", 33188, 5, -1, true, -1, -1]);
        // `json.dumps(["file", os.fsdecode(b"/w/\xff/\xc3\xb6/\xf0\x9f\x98\x80\x7f\n\""), ...],
        // separators=(",", ":"))`
        assert_eq!(
            String::from_utf8(python_json(&entry)).unwrap(),
            r#"["file","/w/\udcff/\u00f6/\ud83d\ude00\u007f\n\"","file",33188,5,-1,true,-1,-1]"#
        );
    }

    #[test]
    fn a_lone_opener_begins_again_and_a_second_does_not() {
        let dir = tempfile::tempdir().unwrap();
        let base = dir.path().join("shadows").join("abc");
        std::fs::create_dir_all(base.parent().unwrap()).unwrap();
        std::fs::write(suffixed(&base, ".journal"), b"[\"dirty\",\"/old\"]\n").unwrap();
        let mut one = Ledger::open(&base).unwrap();
        assert_eq!(
            std::fs::metadata(suffixed(&base, ".journal"))
                .unwrap()
                .len(),
            0
        );
        assert!(one.enter().unwrap().is_empty());
        one.tell(&serde_json::json!(["dirty", "/w/a"]));
        one.exit();

        let mut other = Ledger::open(&base).unwrap();
        assert_eq!(
            other.enter().unwrap(),
            vec![serde_json::json!(["dirty", "/w/a"])]
        );
        other.exit();
        drop((one, other));

        let _alone = Ledger::open(&base).unwrap();
        assert_eq!(
            std::fs::metadata(suffixed(&base, ".journal"))
                .unwrap()
                .len(),
            0
        );
    }

    #[test]
    fn half_lines_are_passed_over_and_entries_nest() {
        let dir = tempfile::tempdir().unwrap();
        let base = dir.path().join("b");
        let mut one = Ledger::open(&base).unwrap();
        let mut other = Ledger::open(&base).unwrap();
        std::fs::OpenOptions::new()
            .append(true)
            .open(suffixed(&base, ".journal"))
            .unwrap()
            .write_all(b"[\"dirty\",\"/half")
            .unwrap();
        one.enter().unwrap();
        one.enter().unwrap();
        one.tell(&serde_json::json!(["forget", "/w/x"]));
        one.exit();
        // Still held: nothing is written until the outermost exit.
        assert_eq!(
            std::fs::metadata(suffixed(&base, ".journal"))
                .unwrap()
                .len(),
            15
        );
        one.exit();
        assert_eq!(
            other.enter().unwrap(),
            vec![serde_json::json!(["forget", "/w/x"])]
        );
        other.exit();
        let written = std::fs::read(suffixed(&base, ".journal")).unwrap();
        assert_eq!(written, b"[\"dirty\",\"/half\n[\"forget\",\"/w/x\"]\n");
    }
}
