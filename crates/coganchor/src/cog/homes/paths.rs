//! The path functions of Python's that `homes.py` leans on, as they behave there:
//! `os.path.realpath` (not strict), `os.path.relpath`, `pathlib`'s spelling of a path,
//! `fnmatch.fnmatchcase`, `Path.glob`, `shutil.copy2` and `shutil.move`.

use std::ffi::{OsStr, OsString};
use std::fs;
use std::io;
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};

use nix::sys::stat::{UtimensatFlags, utimensat};
use nix::sys::time::TimeSpec;

/// `os.path.realpath(path)`: every link in it followed, as far as there is anything to
/// follow; a part that is not there is kept as it is said, and so is a loop.
pub fn realpath(path: &Path) -> PathBuf {
    let said = path.as_os_str().as_bytes();
    let mut resolved: Vec<u8> = if said.starts_with(b"/") {
        b"/".to_vec()
    } else {
        std::env::current_dir()
            .map(|one| one.into_os_string().into_vec())
            .unwrap_or_else(|_| b"/".to_vec())
    };
    // What is left to walk, last part first; `None` marks where a link's target ends, with the
    // link's own path after it, for `seen`.
    let mut rest: Vec<Option<Vec<u8>>> = said
        .split(|one| *one == b'/')
        .rev()
        .map(|one| Some(one.to_vec()))
        .collect();
    let mut seen: std::collections::HashMap<Vec<u8>, Option<Vec<u8>>> =
        std::collections::HashMap::new();
    while let Some(part) = rest.pop() {
        let Some(name) = part else {
            if let Some(Some(link)) = rest.pop() {
                seen.insert(link, Some(resolved.clone()));
            }
            continue;
        };
        if name.is_empty() || name == b"." {
            continue;
        }
        if name == b".." {
            if let Some(at) = resolved.iter().rposition(|one| *one == b'/') {
                resolved.truncate(at.max(1));
            }
            continue;
        }
        let mut joined = resolved.clone();
        if joined != b"/" {
            joined.push(b'/');
        }
        joined.extend_from_slice(&name);
        let joined_path = Path::new(OsStr::from_bytes(&joined));
        match fs::symlink_metadata(joined_path) {
            Ok(meta) if meta.file_type().is_symlink() => {}
            _ => {
                resolved = joined;
                continue;
            }
        }
        if let Some(known) = seen.get(&joined) {
            resolved = known.clone().unwrap_or(joined);
            continue;
        }
        let Ok(target) = fs::read_link(joined_path) else {
            resolved = joined;
            continue;
        };
        let target = target.into_os_string().into_vec();
        seen.insert(joined.clone(), None);
        if target.starts_with(b"/") {
            resolved = b"/".to_vec();
        }
        rest.push(Some(joined));
        rest.push(None);
        rest.extend(
            target
                .split(|one| *one == b'/')
                .rev()
                .map(|one| Some(one.to_vec())),
        );
    }
    PathBuf::from(OsString::from_vec(resolved))
}

/// `pathlib.PurePosixPath(said)`: repeated slashes and `.` parts dropped, and a trailing slash.
pub fn pure(said: &str) -> PathBuf {
    let parts: Vec<&str> = said
        .split('/')
        .filter(|one| !one.is_empty() && *one != ".")
        .collect();
    let joined = parts.join("/");
    if said.starts_with('/') {
        PathBuf::from(format!("/{joined}"))
    } else if joined.is_empty() {
        PathBuf::from(".")
    } else {
        PathBuf::from(joined)
    }
}

/// `os.path.abspath`: absolute and normalised, `..` taken lexically.
fn abspath(path: &Path) -> Vec<Vec<u8>> {
    let mut joined = if path.is_absolute() {
        PathBuf::new()
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/"))
    };
    joined.push(path);
    let mut parts: Vec<Vec<u8>> = Vec::new();
    for one in joined.as_os_str().as_bytes().split(|one| *one == b'/') {
        match one {
            b"" | b"." => {}
            b".." => {
                parts.pop();
            }
            _ => parts.push(one.to_vec()),
        }
    }
    parts
}

/// `os.path.relpath(path, start)`.
pub fn relpath(path: &Path, start: &Path) -> String {
    let path = abspath(path);
    let start = abspath(start);
    let common = path
        .iter()
        .zip(&start)
        .take_while(|(one, other)| one == other)
        .count();
    let mut parts: Vec<Vec<u8>> = vec![b"..".to_vec(); start.len() - common];
    parts.extend(path[common..].iter().cloned());
    if parts.is_empty() {
        return ".".to_owned();
    }
    String::from_utf8_lossy(&parts.join(&b'/')).into_owned()
}

/// `fnmatch.fnmatchcase(name, pattern)`: `*`, `?`, `[...]` and `[!...]`, matching the whole
/// name, `/` and a leading dot included.
pub fn fnmatch(name: &str, pattern: &str) -> bool {
    let name: Vec<char> = name.chars().collect();
    let tokens = tokens(pattern);
    matches(&name, &tokens)
}

#[derive(Debug)]
enum Token {
    Literal(char),
    Any,
    Star,
    Class {
        negated: bool,
        items: Vec<(char, char)>,
    },
}

/// A pattern's tokens, as `fnmatch._translate` reads it: a `[` with no `]` after it is itself.
fn tokens(pattern: &str) -> Vec<Token> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut out = Vec::new();
    let mut index = 0;
    while index < chars.len() {
        let one = chars[index];
        index += 1;
        match one {
            '*' => {
                if !matches!(out.last(), Some(Token::Star)) {
                    out.push(Token::Star);
                }
            }
            '?' => out.push(Token::Any),
            '[' => {
                let mut end = index;
                if chars.get(end) == Some(&'!') {
                    end += 1;
                }
                if chars.get(end) == Some(&']') {
                    end += 1;
                }
                while end < chars.len() && chars[end] != ']' {
                    end += 1;
                }
                if end >= chars.len() {
                    out.push(Token::Literal('['));
                    continue;
                }
                let mut inside = &chars[index..end];
                index = end + 1;
                let negated = inside.first() == Some(&'!');
                if negated {
                    inside = &inside[1..];
                }
                let mut items = Vec::new();
                let mut at = 0;
                while at < inside.len() {
                    if at + 2 < inside.len() && inside[at + 1] == '-' {
                        // A range whose ends are out of order is dropped, as Python drops it.
                        if inside[at] <= inside[at + 2] {
                            items.push((inside[at], inside[at + 2]));
                        }
                        at += 3;
                    } else {
                        items.push((inside[at], inside[at]));
                        at += 1;
                    }
                }
                out.push(Token::Class { negated, items });
            }
            _ => out.push(Token::Literal(one)),
        }
    }
    out
}

/// Whether one character fits a token that is not a star.
fn fits(token: &Token, one: char) -> bool {
    match token {
        Token::Literal(said) => *said == one,
        Token::Any => true,
        // A class whose ranges were all dropped matches nothing, and negated, anything.
        Token::Class { negated, items } => {
            items.iter().any(|(low, high)| *low <= one && one <= *high) != *negated
        }
        Token::Star => false,
    }
}

/// The whole name against the tokens: each star taking as little as it can, and a character
/// more each time what follows does not match -- linear in the name per star.
fn matches(name: &[char], tokens: &[Token]) -> bool {
    let (mut at, mut token) = (0, 0);
    let mut star: Option<(usize, usize)> = None;
    while at < name.len() {
        match tokens.get(token) {
            Some(Token::Star) => {
                star = Some((token, at));
                token += 1;
            }
            Some(one) if fits(one, name[at]) => {
                at += 1;
                token += 1;
            }
            _ => match star {
                Some((was, from)) => {
                    token = was + 1;
                    at = from + 1;
                    star = Some((was, from + 1));
                }
                None => return false,
            },
        }
    }
    tokens[token..].iter().all(|one| matches!(one, Token::Star))
}

/// `sorted(at.glob(pattern))`, for a pattern of names parted by `/`: each part a name or an
/// `fnmatch` pattern matched against every entry of the directory before it, hidden ones
/// included. (`**` is taken as `*`: no record a CLI keeps is said with one.)
pub fn glob(at: &Path, pattern: &str) -> Vec<PathBuf> {
    let mut found = vec![at.to_path_buf()];
    let parts: Vec<&str> = pattern
        .split('/')
        .filter(|one| !one.is_empty() && *one != ".")
        .collect();
    for (index, part) in parts.iter().enumerate() {
        let last = index + 1 == parts.len();
        let wild = part.contains(['*', '?', '[']);
        let mut next = Vec::new();
        for one in found {
            if !wild {
                let joined = one.join(part);
                let there = if last {
                    fs::symlink_metadata(&joined).is_ok()
                } else {
                    joined.is_dir()
                };
                if there {
                    next.push(joined);
                }
                continue;
            }
            let Ok(entries) = fs::read_dir(&one) else {
                continue;
            };
            for entry in entries.flatten() {
                let name = entry.file_name();
                let Some(name) = name.to_str() else { continue };
                if fnmatch(name, part) && (last || entry.path().is_dir()) {
                    next.push(entry.path());
                }
            }
        }
        found = next;
    }
    if parts.is_empty() {
        return Vec::new();
    }
    found.sort();
    found
}

/// `shutil.copy2(source, into)`: what `source` holds, links followed, with its mode and its
/// times.
pub fn copy2(source: &Path, into: &Path) -> io::Result<()> {
    let meta = fs::metadata(source)?;
    fs::copy(source, into)?;
    utime(into, &meta)
}

/// `os.utime(at, ns=(atime, mtime))` of another file's times.
pub fn utime(at: &Path, meta: &fs::Metadata) -> io::Result<()> {
    use std::os::unix::fs::MetadataExt;
    let atime = TimeSpec::new(meta.atime(), meta.atime_nsec());
    let mtime = TimeSpec::new(meta.mtime(), meta.mtime_nsec());
    utimensat(
        nix::fcntl::AT_FDCWD,
        at,
        &atime,
        &mtime,
        UtimensatFlags::FollowSymlink,
    )
    .map_err(io::Error::from)
}

/// `shutil.move(source, into)` for an `into` that is not there: a rename, or where that
/// fails -- across devices -- a copy of it, links copied as links, and the source removed.
pub fn move_to(source: &Path, into: &Path) -> io::Result<()> {
    if fs::rename(source, into).is_ok() {
        return Ok(());
    }
    let meta = fs::symlink_metadata(source)?;
    if meta.file_type().is_symlink() {
        std::os::unix::fs::symlink(fs::read_link(source)?, into)?;
        return fs::remove_file(source);
    }
    if meta.is_dir() {
        copytree(source, into)?;
        return fs::remove_dir_all(source);
    }
    copy2(source, into)?;
    fs::remove_file(source)
}

/// `shutil.copytree(source, into, symlinks=True)`.
pub(crate) fn copytree(source: &Path, into: &Path) -> io::Result<()> {
    fs::create_dir(into)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let (from, to) = (entry.path(), into.join(entry.file_name()));
        let kind = entry.file_type()?;
        if kind.is_symlink() {
            std::os::unix::fs::symlink(fs::read_link(&from)?, &to)?;
        } else if kind.is_dir() {
            copytree(&from, &to)?;
        } else {
            copy2(&from, &to)?;
        }
    }
    let meta = fs::metadata(source)?;
    fs::set_permissions(into, meta.permissions())?;
    utime(into, &meta)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_match_as_fnmatch_matches_them() {
        for (name, pattern, wanted) in [
            ("state_5.sqlite", "state_*.sqlite", true),
            ("state_5.sqlite-wal", "state_*.sqlite*", true),
            ("state_5.sqlite-wal", "state_*.sqlite", false),
            (".hidden", "*", true),
            ("a/b", "a*b", true),
            ("sessions", "sess*", true),
            ("x", "[!a-c]", true),
            ("b", "[!a-c]", false),
            ("b", "[a-c]", true),
            ("[", "[", true),
            ("]", "[]]", true),
            ("ab", "a?", true),
            ("a", "a?", false),
            ("z", "[z-a]", false),
            ("z", "[!z-a]", true),
            (
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "*a*a*a*a*a*a*a*a*b",
                false,
            ),
            ("xay", "*a*", true),
            ("", "*", true),
            ("", "?", false),
        ] {
            assert_eq!(fnmatch(name, pattern), wanted, "{name} {pattern}");
        }
    }

    #[test]
    fn paths_are_spelled_and_related_as_python_does() {
        assert_eq!(pure("/a//b/./c/"), PathBuf::from("/a/b/c"));
        assert_eq!(pure("./a"), PathBuf::from("a"));
        assert_eq!(
            relpath(Path::new("/tmp/x/h"), Path::new("/home/u/.gemini")),
            "../../../tmp/x/h"
        );
        assert_eq!(relpath(Path::new("/a/b"), Path::new("/a/b")), ".");
        assert_eq!(relpath(Path::new("/a/b/c"), Path::new("/a")), "b/c");
    }

    #[test]
    fn realpath_follows_what_is_there_and_keeps_what_is_not() {
        let root = tempfile::tempdir().expect("a directory");
        let root = fs::canonicalize(root.path()).expect("its name");
        fs::create_dir(root.join("real")).expect("made");
        std::os::unix::fs::symlink(root.join("real"), root.join("link")).expect("linked");
        std::os::unix::fs::symlink("loop", root.join("loop")).expect("linked");
        assert_eq!(
            realpath(&root.join("link/missing/x")),
            root.join("real/missing/x")
        );
        assert_eq!(realpath(&root.join("link/../link")), root.join("real"));
        assert_eq!(realpath(&root.join("loop")), root.join("loop"));
    }
}
