//! What a native turn does on this machine: finding the files it carries, telling a sign-in
//! that refreshes itself, and writing one back whole.
//!
//! `refreshes`/`refreshing` are `hmz.coganchor._lending`'s, `writes` is
//! `hmz.coganchor.atomic.writes`, and `normpath`/`join` are `posixpath`'s. Unit 12's
//! `lending` declares only `lent`, so the rest of `_lending` lives here until it says more.

use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::io::{self, Read, Write};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

use crate::proto::json;

/// How much of a file is read to ask whether it is a sign-in (`_lending._AT_MOST`).
const AT_MOST: u64 = 1 << 20;

/// `posixpath.normpath`.
pub(super) fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".into();
    }
    let slashes = path.len() - path.trim_start_matches('/').len();
    let lead = match slashes {
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
            ".." if !lead.is_empty() => {}
            _ => parts.push(part),
        }
    }
    let joined = format!("{lead}{}", parts.join("/"));
    if joined.is_empty() {
        ".".into()
    } else {
        joined
    }
}

/// `posixpath.join` of two parts.
pub(super) fn join(head: &str, tail: &str) -> String {
    if tail.starts_with('/') {
        tail.to_owned()
    } else if head.is_empty() || head.ends_with('/') {
        format!("{head}{tail}")
    } else {
        format!("{head}/{tail}")
    }
}

/// `posixpath.join` of a head and any number of parts.
pub(super) fn joined<'a>(head: &str, parts: impl IntoIterator<Item = &'a str>) -> String {
    parts
        .into_iter()
        .fold(head.to_owned(), |at, part| join(&at, part))
}

/// `posixpath.relpath` of two absolute paths.
pub(super) fn relpath(path: &str, start: &str) -> String {
    let parts = |said: &str| -> Vec<String> {
        normpath(said)
            .split('/')
            .filter(|part| !part.is_empty())
            .map(str::to_owned)
            .collect()
    };
    let (to, from) = (parts(path), parts(start));
    let common = to
        .iter()
        .zip(&from)
        .take_while(|(one, other)| one == other)
        .count();
    let mut rel: Vec<&str> = vec![".."; from.len() - common];
    rel.extend(to[common..].iter().map(String::as_str));
    if rel.is_empty() {
        ".".into()
    } else {
        rel.join("/")
    }
}

/// Every file under `root`, as `sorted(p for p in Path(root).rglob("*") if p.is_file())`
/// finds them: directories not followed through a link, a link to a file counted, in the order
/// of their parts. Each comes with its parts under `root`, spelled as the wire spells them.
pub(super) fn files(root: &str) -> Vec<(PathBuf, Vec<String>)> {
    let mut found = Vec::new();
    walk(Path::new(&normpath(root)), &mut Vec::new(), &mut found);
    found.sort_by(|(_, one), (_, other)| one.cmp(other));
    found
        .into_iter()
        .map(|(path, parts)| {
            let spelled = parts.iter().map(|part| json::from_os(part)).collect();
            (path, spelled)
        })
        .collect()
}

fn walk(at: &Path, under: &mut Vec<OsString>, found: &mut Vec<(PathBuf, Vec<OsString>)>) {
    let Ok(entries) = fs::read_dir(at) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        under.push(entry.file_name());
        match entry.file_type() {
            Ok(kind) if kind.is_dir() => walk(&path, under, found),
            Ok(_) if path.is_file() => found.push((path, under.clone())),
            _ => {}
        }
        under.pop();
    }
}

/// Whether some bytes hold a refresh token, in any spelling `_lending.REFRESHES` knows:
/// `refresh[_-]?token`, or `"refresh":` (either quote, any space before the colon), any case.
pub(super) fn refreshes(said: &[u8]) -> bool {
    let low = said.to_ascii_lowercase();
    let at = |from: usize, word: &[u8]| low.get(from..).is_some_and(|rest| rest.starts_with(word));
    let quote = |from: usize| matches!(low.get(from), Some(b'"' | b'\''));
    (0..low.len()).filter(|i| at(*i, b"refresh")).any(|i| {
        let after = i + b"refresh".len();
        if at(after, b"token")
            || (matches!(low.get(after), Some(b'_' | b'-')) && at(after + 1, b"token"))
        {
            return true;
        }
        if i == 0 || !quote(i - 1) || !quote(after) {
            return false;
        }
        let mut next = after + 1;
        while matches!(
            low.get(next),
            Some(b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
        ) {
            next += 1;
        }
        low.get(next) == Some(&b':')
    })
}

/// Whether a file is a sign-in that refreshes itself (`_lending.refreshes`).
fn refreshes_file(path: &Path) -> bool {
    let mut said = Vec::new();
    match fs::File::open(path) {
        Ok(file) => file.take(AT_MOST).read_to_end(&mut said).is_ok() && refreshes(&said),
        Err(_) => false,
    }
}

/// The sign-ins that refresh themselves among some credential paths, each a file or a
/// directory of them (`_lending.refreshing`, looking inside): `os.walk`'s files, which is
/// every entry that is not a directory once links are followed.
pub(super) fn refreshing<'a>(roots: impl IntoIterator<Item = &'a str>) -> BTreeSet<PathBuf> {
    let mut found = BTreeSet::new();
    for root in roots {
        let root = PathBuf::from(normpath(root));
        if root.is_file() {
            if refreshes_file(&root) {
                found.insert(root);
            }
            continue;
        }
        let mut pending = vec![root];
        while let Some(at) = pending.pop() {
            let Ok(entries) = fs::read_dir(&at) else {
                continue;
            };
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
                        pending.push(path);
                    }
                } else if refreshes_file(&path) {
                    found.insert(path);
                }
            }
        }
    }
    found
}

/// Whether some bytes are a whole JSON document, as every sign-in file of these CLIs is
/// (`anchor._json`).
pub(super) fn is_json(said: &[u8]) -> bool {
    serde_json::from_slice::<serde_json::Value>(said).is_ok()
}

/// Replaces a file with `said`, whole and on disk before it is moved into place, keeping the
/// mode it had, or giving one not there yet what the umask leaves of `0666`
/// (`atomic.writes`, mode None).
pub(super) fn writes(at: &Path, said: &[u8]) -> io::Result<()> {
    let keeps = match fs::metadata(at) {
        Ok(found) => Some(found.permissions().mode() & 0o7777),
        Err(why) if why.kind() == io::ErrorKind::NotFound => None,
        Err(why) => return Err(why),
    };
    let name = at.file_name().map(OsStrExt::as_bytes).unwrap_or_default();
    let (beside, mut file) = loop {
        let mut called = b".".to_vec();
        called.extend_from_slice(name);
        called.extend_from_slice(
            format!(".{}.new", hex::encode(rand::random::<[u8; 8]>())).as_bytes(),
        );
        let beside = at.with_file_name(std::ffi::OsStr::from_bytes(&called));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(if keeps.is_none() { 0o666 } else { 0o600 })
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

/// The path with every link on the way resolved, as far as there is anything to resolve
/// (`os.path.realpath`, not strict). `path` is absolute.
pub(super) fn resolved(path: &Path) -> PathBuf {
    let mut out = PathBuf::from("/");
    let mut pending: Vec<OsString> = path
        .components()
        .rev()
        .map(|part| part.as_os_str().to_owned())
        .collect();
    let mut hops = 0;
    while let Some(part) = pending.pop() {
        match part.as_bytes() {
            b"/" | b"" | b"." => continue,
            b".." => {
                out.pop();
                continue;
            }
            _ => {}
        }
        let next = out.join(&part);
        match fs::read_link(&next) {
            Ok(target) if hops < 40 => {
                hops += 1;
                if target.is_absolute() {
                    out = PathBuf::from("/");
                }
                pending.extend(
                    target
                        .components()
                        .rev()
                        .map(|one| one.as_os_str().to_owned()),
                );
            }
            _ => out = next,
        }
    }
    out
}

/// Whether `path` is `root` or inside it (`os.path.commonpath([path, root]) == root`).
pub(super) fn within(path: &Path, root: &Path) -> bool {
    path.starts_with(root)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normpath_is_posixpaths() {
        for (said, meant) in [
            ("", "."),
            ("/", "/"),
            ("//a", "//a"),
            ("///a/", "/a"),
            ("a/./b/../c", "a/c"),
            ("../a", "../a"),
            ("/../a", "/a"),
            ("a/..", "."),
        ] {
            assert_eq!(normpath(said), meant, "{said}");
        }
    }

    #[test]
    fn relpath_is_posixpaths() {
        assert_eq!(relpath("/h/.claude/x", "/h"), ".claude/x");
        assert_eq!(relpath("/h/a/../b", "/h/"), "b");
        assert_eq!(relpath("/h", "/h"), ".");
        assert_eq!(relpath("/h/..", "/h"), "..");
        assert_eq!(relpath("/a", "/"), "a");
    }

    #[test]
    fn join_is_posixpaths() {
        assert_eq!(join("/s", "codex_home"), "/s/codex_home");
        assert_eq!(join("/s/", "x"), "/s/x");
        assert_eq!(join("/s", ""), "/s/");
        assert_eq!(join("/s", "/abs"), "/abs");
        assert_eq!(
            joined("/s/h", ["", "review", "SKILL.md"]),
            "/s/h/review/SKILL.md"
        );
    }

    #[test]
    fn refresh_tokens_are_told_in_every_spelling() {
        for said in [
            &br#"{"tokens": {"refresh_token": "r"}}"#[..],
            br#"{"refreshToken": "r"}"#,
            br#"{"REFRESH-TOKEN": 1}"#,
            br#"{"refresh" : "r"}"#,
            br#"{'refresh':"r"}"#,
        ] {
            assert!(refreshes(said), "{}", String::from_utf8_lossy(said));
        }
        for said in [
            &br#"{"OPENAI_API_KEY": "sk-a"}"#[..],
            br#"{"refresh": }"#.split_at(9).0,
            br#"{"refreshes": 1}"#,
            br#"refresh"#,
        ] {
            assert!(!refreshes(said), "{}", String::from_utf8_lossy(said));
        }
    }

    #[test]
    fn files_are_found_as_rglob_finds_them() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        fs::create_dir_all(root.join("a")).unwrap();
        fs::create_dir_all(root.join("elsewhere")).unwrap();
        fs::write(root.join("a/x"), "").unwrap();
        fs::write(root.join("a-b"), "").unwrap();
        fs::write(root.join("elsewhere/y"), "").unwrap();
        std::os::unix::fs::symlink(root.join("a/x"), root.join("linked")).unwrap();
        std::os::unix::fs::symlink(root.join("elsewhere"), root.join("z")).unwrap();
        let found: Vec<Vec<String>> = files(root.to_str().unwrap())
            .into_iter()
            .map(|(_, parts)| parts)
            .collect();
        assert_eq!(
            found,
            [
                vec!["a", "x"],
                vec!["a-b"],
                vec!["elsewhere", "y"],
                vec!["linked"],
            ]
        );
        assert!(files("/no/such/place").is_empty());
    }

    #[test]
    fn writes_keep_the_mode_and_leave_nothing_beside() {
        let dir = tempfile::tempdir().unwrap();
        let at = dir.path().join("auth.json");
        fs::write(&at, "old").unwrap();
        fs::set_permissions(&at, fs::Permissions::from_mode(0o600)).unwrap();
        writes(&at, b"new").unwrap();
        assert_eq!(fs::read(&at).unwrap(), b"new");
        assert_eq!(
            fs::metadata(&at).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn resolving_follows_links_as_far_as_they_go() {
        let dir = tempfile::tempdir().unwrap();
        let root = resolved(dir.path());
        std::os::unix::fs::symlink("/etc", root.join("out")).unwrap();
        assert_eq!(
            resolved(&root.join("out/x")),
            resolved(Path::new("/etc")).join("x")
        );
        assert_eq!(resolved(&root.join("a/../b")), root.join("b"));
        assert!(!within(&resolved(&root.join("out")), &root));
        assert!(within(&root.join("b"), &root));
    }
}
