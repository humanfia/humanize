//! A sign-in that refreshes itself, held by one machine's turns at a time. Port of
//! `hmz.coganchor._lending` (the Python module stays for its other callers; the lock must
//! interoperate with it). [Unit 12]
//!
//! `flock` on the directory of each credential file holding a refresh token: shared for turns
//! here, exclusive for the one copy lent away; never waited for (`EBUSY` instead).
//!
//! Each refresh writes a new refresh token and spends the one it replaced, and a spent one
//! presented again gets the whole family revoked. So such a file is never in two places that
//! refresh apart: every turn here shares it (one holder), and a copy sent to another machine is
//! let out only while no turn here holds it. A lock rather than a note, so a turn killed
//! outright gives it up with its process; the same `flock` on the same directory as Python
//! takes, so a Rust cog and a Python turn exclude each other.

use std::collections::BTreeSet;
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::AsRawFd;
use std::path::{Path, PathBuf};

/// What every refusal here says, which is also what a failed turn is known by
/// (`hmz.coganchor.backends.SIGNS`).
pub const SAID: &str = "signs in with a token that refreshes itself";

/// How much of a file is read to ask whether it is a sign-in (`_AT_MOST`).
const AT_MOST: u64 = 1 << 20;

/// The locks held for a session; released when dropped.
pub struct Lent {
    held: Vec<std::fs::File>,
}

/// Whether `content` holds a refresh token, in any spelling `REFRESHES` knows: the bytes
/// pattern `refresh[_-]?token|["']refresh["']\s*:`, ASCII case ignored, as Python's
/// `re.IGNORECASE` reads a bytes pattern.
pub fn holds_refresh_token(content: &[u8]) -> bool {
    const WORD: &[u8] = b"refresh";
    let quote = |byte: Option<&u8>| matches!(byte, Some(b'"' | b'\''));
    let lower: Vec<u8> = content.to_ascii_lowercase();
    let mut from = 0;
    while let Some(found) = lower[from..]
        .windows(WORD.len())
        .position(|window| window == WORD)
    {
        let at = from + found;
        let after = at + WORD.len();
        let rest = &lower[after..];
        let token = rest.starts_with(b"token")
            || (matches!(rest.first(), Some(b'_' | b'-')) && rest[1..].starts_with(b"token"));
        if token {
            return true;
        }
        if at > 0 && quote(lower.get(at - 1)) && quote(rest.first()) {
            // `\s` of a bytes pattern: space, \t, \n, \r, \f, \v.
            let colon = rest[1..]
                .iter()
                .find(|byte| !matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c));
            if colon == Some(&b':') {
                return true;
            }
        }
        from = at + 1;
    }
    false
}

/// Whether a file is a sign-in that refreshes itself (`refreshes`): its first MiB holds a
/// refresh token. One that cannot be read is not.
pub fn refreshes(path: &Path) -> bool {
    let mut content = Vec::new();
    match File::open(path).and_then(|file| file.take(AT_MOST).read_to_end(&mut content)) {
        Ok(_) => holds_refresh_token(&content),
        Err(_) => false,
    }
}

/// The sign-ins that refresh themselves among some credential paths (`refreshing`): each root
/// a file, or -- `inside` -- a directory walked for them without following links into other
/// directories. Not `inside` where a directory may be a CLI's sessions, which are thousands of
/// files and a transcript may mention a refresh token.
pub fn refreshing<P: AsRef<Path>>(roots: &[P], inside: bool) -> BTreeSet<PathBuf> {
    let mut found = BTreeSet::new();
    for root in roots {
        let root = normalised(root.as_ref());
        if root.is_file() {
            if refreshes(&root) {
                found.insert(root);
            }
        } else if inside && root.is_dir() {
            walk(&root, &mut found);
        }
    }
    found
}

fn walk(directory: &Path, found: &mut BTreeSet<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        // As `os.walk` sorts them: a link to a directory is a directory, and is not entered.
        if path.is_dir() {
            if entry.file_type().is_ok_and(|kind| !kind.is_symlink()) {
                walk(&path, found);
            }
        } else if refreshes(&path) {
            found.insert(path);
        }
    }
}

/// `os.path.normpath` of a path that may be relative.
fn normalised(path: &Path) -> PathBuf {
    let said = path.to_string_lossy();
    if said.starts_with('/') {
        PathBuf::from(crate::cog::config::normpath(&said))
    } else {
        path.to_path_buf()
    }
}

/// Takes the locks for `files` that hold refresh tokens: exclusive where `away`.
///
/// `files` are those [`refreshing`] found, taken as found: read again here, one being
/// rewritten as the turn starts could read as no sign-in and go unheld. Each directory such a
/// file is in is locked once (`flock`, `LOCK_SH` or `LOCK_EX`, never
/// waiting). A directory that is gone is nothing left to hold; one that cannot be locked for
/// another reason -- NFS, which emulates these with locks a read-only descriptor cannot take
/// exclusively -- is said and left unheld, since refusing every turn of the account there
/// would be refusing to run.
///
/// # Errors
/// `EBUSY` (`ErrorKind::ResourceBusy`) where one is held the other way already: a copy is out
/// on another machine, or -- for one about to be copied -- a turn here is using it.
pub fn lent(files: &[PathBuf], away: bool) -> io::Result<Lent> {
    let directories: BTreeSet<PathBuf> = files
        .iter()
        .filter_map(|file| file.parent().map(Path::to_path_buf))
        .collect();
    let how = if away { libc::LOCK_EX } else { libc::LOCK_SH };
    let mut held = Vec::new();
    for directory in directories {
        let Ok(opened) = File::open(&directory) else {
            continue;
        };
        // SAFETY: `flock` on a descriptor this function owns.
        if unsafe { libc::flock(opened.as_raw_fd(), how | libc::LOCK_NB) } == 0 {
            held.push(opened);
            continue;
        }
        let why = io::Error::last_os_error();
        if why.raw_os_error() == Some(libc::EWOULDBLOCK) {
            return Err(busy(&directory, away));
        }
        tracing::warn!(
            "cannot hold {} for this turn: {}",
            directory.display(),
            crate::cog::config::os_said(&why, None)
        );
    }
    Ok(Lent { held })
}

/// The refusal, worded as Python words it: `[Errno 16] <why>: '<directory>'`.
fn busy(directory: &Path, away: bool) -> io::Error {
    let why = if away {
        format!(
            "this account {SAID}, and another turn is using it, so no copy of it can go to \
             another machine now -- two copies refreshing apart get the sign-in revoked; run \
             this turn on this machine, or give it an account signed in with a key"
        )
    } else {
        format!(
            "this account {SAID}, and a copy of it is out on another machine for a turn there \
             -- two copies refreshing apart get the sign-in revoked; this turn can run once \
             that one is over"
        )
    };
    io::Error::new(
        io::ErrorKind::ResourceBusy,
        format!(
            "[Errno {}] {why}: {}",
            libc::EBUSY,
            crate::cog::config::py_repr(&directory.to_string_lossy())
        ),
    )
}

impl Lent {
    /// How many directories are held.
    pub fn len(&self) -> usize {
        self.held.len()
    }

    /// Whether nothing is held.
    pub fn is_empty(&self) -> bool {
        self.held.is_empty()
    }
}

#[cfg(test)]
mod tests {
    //! The lending cases, and the lock seen from both languages: a lock Rust takes is one
    //! `hmz.coganchor._lending` finds busy, and the other way about.

    use super::*;

    /// Held by every test that locks: a child another test forks holds a copy of each
    /// descriptor open at that moment, and so of its lock, until it has `exec`ed.
    static ONE_AT_A_TIME: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn alone() -> std::sync::MutexGuard<'static, ()> {
        ONE_AT_A_TIME
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn signed_in(dir: &Path, name: &str, content: &str) -> PathBuf {
        let file = dir.join(name);
        std::fs::write(&file, content).unwrap();
        file
    }

    #[test]
    fn every_spelling_of_a_refresh_token_is_one() {
        for said in [
            r#"{"refresh_token": "x"}"#,
            r#"{"refreshToken": "x"}"#,
            "REFRESH-TOKEN=x",
            r#"{"refresh" : "x"}"#,
            "{'refresh':\n 'x'}",
        ] {
            assert!(holds_refresh_token(said.as_bytes()), "{said}");
        }
        for said in [
            r#"{"api_key": "x"}"#,
            r#"{"refresh" = true"#,
            "refresh token",
            r#"refresh": 1"#,
            "",
        ] {
            assert!(!holds_refresh_token(said.as_bytes()), "{said}");
        }
    }

    #[test]
    fn only_files_that_refresh_are_found_and_directories_only_inside() {
        let dir = tempfile::tempdir().unwrap();
        let auth = signed_in(dir.path(), "auth.json", r#"{"refresh_token":"x"}"#);
        signed_in(dir.path(), "key.json", r#"{"api_key":"x"}"#);
        let roots = [auth.clone(), dir.path().join("missing")];
        assert_eq!(refreshing(&roots, false), BTreeSet::from([auth.clone()]));
        assert!(refreshing(&[dir.path()], false).is_empty());
        assert_eq!(refreshing(&[dir.path()], true), BTreeSet::from([auth]));
    }

    #[test]
    fn turns_here_share_and_a_copy_away_excludes_them() {
        let _alone = alone();
        let dir = tempfile::tempdir().unwrap();
        let auth = signed_in(dir.path(), "auth.json", r#"{"refreshToken":"x"}"#);
        let files = [auth];
        let one = lent(&files, false).unwrap();
        let two = lent(&files, false).unwrap();
        assert_eq!(one.len(), 1);
        let refused = lent(&files, true).err().unwrap();
        assert_eq!(refused.kind(), io::ErrorKind::ResourceBusy);
        assert!(
            refused
                .to_string()
                .starts_with("[Errno 16] this account signs in")
        );
        drop((one, two));
        let away = lent(&files, true).unwrap();
        let refused = lent(&files, false).err().unwrap();
        assert!(
            refused
                .to_string()
                .contains("a copy of it is out on another machine")
        );
        drop(away);
        lent(&files, false).unwrap();
    }

    #[test]
    fn a_directory_that_is_gone_is_nothing_to_hold() {
        let _alone = alone();
        let dir = tempfile::tempdir().unwrap();
        let gone = dir.path().join("gone").join("auth.json");
        assert!(lent(&[gone], true).unwrap().is_empty());
    }

    /// The repository root, where `uv run` finds `hmz`.
    fn repository() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
    }

    /// The Python `uv run` gives this repository, asked once, where it imports `hmz`.
    fn interpreter() -> Option<&'static PathBuf> {
        use std::process::{Command, Stdio};
        static FOUND: std::sync::OnceLock<Option<PathBuf>> = std::sync::OnceLock::new();
        FOUND
            .get_or_init(|| {
                let said = Command::new("uv")
                    .args(["run", "--quiet", "python", "-c"])
                    .arg("import sys, hmz.coganchor._lending; print(sys.executable)")
                    .current_dir(repository())
                    .stderr(Stdio::null())
                    .output()
                    .ok()
                    .filter(|said| said.status.success())?;
                let path = String::from_utf8(said.stdout).ok()?;
                Some(PathBuf::from(path.trim()))
            })
            .as_ref()
    }

    /// Runs Python with `hmz` importable, or None where it cannot be (no `uv`, or no `hmz`).
    fn python(script: &str) -> Option<std::process::Child> {
        use std::process::{Command, Stdio};
        let Some(interpreter) = interpreter() else {
            eprintln!("skipped: hmz.coganchor._lending cannot be imported through uv here");
            return None;
        };
        Command::new(interpreter)
            .args(["-c", script])
            .current_dir(repository())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .ok()
    }

    const TAKE: &str = r#"
import sys
from hmz.coganchor._lending import lent
try:
    with lent([sys.argv[1]], away=sys.argv[2] == "away"):
        print("held", flush=True)
        sys.stdin.read()
except OSError as why:
    print(f"busy {why.errno}", flush=True)
"#;

    fn ask_python(file: &Path, away: bool) -> Option<(std::process::Child, String)> {
        use std::io::BufRead;
        let script = format!(
            "import sys; sys.argv[1:] = [{:?}, {:?}]\n{TAKE}",
            file.to_str().unwrap(),
            if away { "away" } else { "here" }
        );
        let mut child = python(&script)?;
        let mut line = String::new();
        io::BufReader::new(child.stdout.as_mut().unwrap())
            .read_line(&mut line)
            .unwrap();
        Some((child, line.trim().to_owned()))
    }

    #[test]
    fn a_lock_rust_takes_is_one_python_finds_busy() {
        let _alone = alone();
        let dir = tempfile::tempdir().unwrap();
        let auth = signed_in(dir.path(), "auth.json", r#"{"refresh_token":"x"}"#);
        let here = lent(std::slice::from_ref(&auth), false).unwrap();
        let Some((mut child, said)) = ask_python(&auth, true) else {
            return;
        };
        drop(child.stdin.take());
        child.wait().unwrap();
        assert_eq!(said, format!("busy {}", libc::EBUSY));
        // Shared with shared is no conflict, in either language.
        let (mut child, said) = ask_python(&auth, false).unwrap();
        drop(child.stdin.take());
        child.wait().unwrap();
        assert_eq!(said, "held");
        drop(here);
    }

    #[test]
    fn a_lock_python_takes_is_one_rust_finds_busy() {
        let _alone = alone();
        let dir = tempfile::tempdir().unwrap();
        let auth = signed_in(dir.path(), "auth.json", r#"{"refresh_token":"x"}"#);
        let Some((mut child, said)) = ask_python(&auth, true) else {
            return;
        };
        assert_eq!(said, "held");
        let refused = lent(std::slice::from_ref(&auth), false).err();
        drop(child.stdin.take());
        child.wait().unwrap();
        assert_eq!(refused.unwrap().kind(), io::ErrorKind::ResourceBusy);
        lent(&[auth], true).unwrap();
    }
}
