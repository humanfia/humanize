//! What a redirect answers a path with, shared by the cog and the cred tracer. Port of
//! `answered`, `head` and `parents` in `hmz.coganchor.policy`. [Unit 8]
//!
//! A path an agent names may be answered with another one: the credentials of the provider a
//! turn runs as, rather than whichever account this machine is signed into. An entry is
//! `(what the agent names, what it gets)`, either side a path or a pattern whose names may
//! hold a `*`, standing for any run of characters within that one name. `*` is the only
//! wildcard there is, so that a home whose path holds a `[` or a `?` is still the path it
//! spells.

use std::fs;
use std::io;

use crate::cog::statepaths::dirname;

/// What makes a name a pattern rather than a name (`_WILDCARD`).
const WILDCARD: char = '*';

/// What every path one entry answers starts with, as characters: the whole of it for a path,
/// and everything up to its first wildcard for a pattern -- which is what a tracer can hold
/// a path it has read against without working anything out. Port of `policy.head`.
pub fn head(target: &str) -> String {
    match target.find(WILDCARD) {
        Some(at) => target[..at].to_owned(),
        None => target.to_owned(),
    }
}

/// Whether one name is one a name of a pattern answers (`policy._matches`).
///
/// Python compiles the pattern into a regular expression, each `*` becoming `.*`; `.` does
/// not match a newline there, so neither does a wildcard here.
fn matches(name: &str, pattern: &str) -> bool {
    if !pattern.contains(WILDCARD) {
        return name == pattern;
    }
    let pattern: Vec<char> = pattern.chars().collect();
    // can[j]: whether the name so far is matched by the first j characters of the pattern;
    // two rows, swapped per character of the name.
    let mut can = vec![false; pattern.len() + 1];
    let mut next = vec![false; pattern.len() + 1];
    can[0] = true;
    for j in 1..=pattern.len() {
        can[j] = can[j - 1] && pattern[j - 1] == WILDCARD;
    }
    for c in name.chars() {
        next[0] = false;
        for j in 1..=pattern.len() {
            next[j] = if pattern[j - 1] == WILDCARD {
                next[j - 1] || (can[j] && c != '\n')
            } else {
                can[j - 1] && pattern[j - 1] == c
            };
        }
        std::mem::swap(&mut can, &mut next);
    }
    can[pattern.len()]
}

/// What one entry of a table answers one path with. Port of `policy.answered`.
///
/// A path answers three shapes: the file itself, anything inside it where it is a directory,
/// and anything beside it under the same name and another suffix -- how these CLIs rotate a
/// token, writing `.credentials.json.tmp` and renaming it over `.credentials.json`.
///
/// A pattern (`state_*.sqlite*`, `projects/*/chats`) answers every path whose names match
/// its own one for one, and anything inside one. What it is answered with ends in the same
/// names as the pattern does, and what matched them is put in their place.
///
/// `path` is the absolute, normalised path the process named; `None` is a path this entry
/// says nothing about.
pub fn answered_by(named: &str, instead: &str, path: &str) -> Option<String> {
    if !named.contains(WILDCARD) {
        if path == named {
            return Some(instead.to_owned());
        }
        let rest = path.strip_prefix(named)?;
        return (rest.starts_with('/') || rest.starts_with('.'))
            .then(|| format!("{instead}{rest}"));
    }
    let wanted: Vec<&str> = named.split('/').collect();
    let said: Vec<&str> = path.split('/').collect();
    if said.len() < wanted.len()
        || !said
            .iter()
            .zip(&wanted)
            .all(|(one, pattern)| matches(one, pattern))
    {
        return None;
    }
    let fixed = wanted.iter().position(|one| one.contains(WILDCARD))?;
    // `instead.split("/")[: -(len(wanted) - fixed)]`, which is empty where `instead` has
    // fewer names than that.
    let parts: Vec<&str> = instead.split('/').collect();
    let keep = parts.len().saturating_sub(wanted.len() - fixed);
    let joined: Vec<&str> = parts[..keep]
        .iter()
        .chain(&said[fixed..])
        .copied()
        .collect();
    Some(joined.join("/"))
}

/// The path `redirects` answer `path` with (`*` patterns allowed), if any: the first entry,
/// in the order given, that says anything about it. A caller wanting the entry that says most
/// orders them longest named path first, as [`crate::cog::router::Router`] does.
pub fn answered(redirects: &[(String, String)], path: &str) -> Option<String> {
    redirects
        .iter()
        .find_map(|(named, instead)| answered_by(named, instead, path))
}

/// Makes the directory a redirect target that is about to be created is in. Port of
/// `policy.parents`, less its memo of what was made, which the caller keeps.
///
/// Where a session is kept is not made until something is written into it, and a CLI making
/// its own directory with `mkdir -p` would otherwise be told there is nowhere to make it.
/// Python suppresses the error; it is returned here for the caller to drop.
pub fn parents(path: &str) -> io::Result<()> {
    let parent = dirname(path);
    if parent.is_empty() {
        // `os.makedirs("")` fails; there is nothing to make.
        return Err(io::Error::from(io::ErrorKind::NotFound));
    }
    fs::create_dir_all(parent)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn head_is_everything_up_to_the_first_wildcard() {
        for (named, said) in [
            ("/a/b", "/a/b"),
            ("/a/state_*.db", "/a/state_"),
            ("/a/*/x", "/a/"),
            ("", ""),
        ] {
            assert_eq!(head(named), said);
        }
    }

    #[test]
    fn a_path_answers_itself_what_is_inside_and_what_is_beside_it() {
        for (path, answer) in [
            ("/h/c.json", Some("/p/c.json")),
            ("/h/c.json.tmp", Some("/p/c.json.tmp")),
            ("/h/c.json/inside", Some("/p/c.json/inside")),
            ("/h/c.jsonl", None),
            ("/h/other", None),
        ] {
            assert_eq!(
                answered_by("/h/c.json", "/p/c.json", path).as_deref(),
                answer,
                "{path}"
            );
        }
    }

    #[test]
    fn a_pattern_answers_every_path_whose_names_match() {
        for (named, instead, path, answer) in [
            (
                "/h/state_*.db",
                "/p/state_*.db",
                "/h/state_5.db",
                Some("/p/state_5.db"),
            ),
            (
                "/h/state_*.db",
                "/p/state_*.db",
                "/h/state_5.db/x",
                Some("/p/state_5.db/x"),
            ),
            ("/h/state_*.db", "/p/state_*.db", "/h/other.db", None),
            (
                "/h/projects/*/chats",
                "/s/projects/*/chats",
                "/h/projects/a/chats/1",
                Some("/s/projects/a/chats/1"),
            ),
            (
                "/h/projects/*/chats",
                "/s/projects/*/chats",
                "/h/projects",
                None,
            ),
            (
                "/h/projects/*/chats",
                "/s/projects/*/chats",
                "/h/projects/a/logs",
                None,
            ),
            ("/h/*", "/p/*", "/h/a\nb", None),
            ("/h/a*b*c", "/p/x", "/h/aXbYbc", Some("/p/aXbYbc")),
        ] {
            assert_eq!(
                answered_by(named, instead, path).as_deref(),
                answer,
                "{path}"
            );
        }
    }

    #[test]
    fn a_table_answers_by_its_first_entry_that_says_anything() {
        let table = vec![
            ("/h/.c/creds.json".to_owned(), "/p/creds.json".to_owned()),
            ("/h/.c".to_owned(), "/p/all".to_owned()),
        ];
        assert_eq!(
            answered(&table, "/h/.c/creds.json").as_deref(),
            Some("/p/creds.json")
        );
        assert_eq!(answered(&table, "/h/.c/x").as_deref(), Some("/p/all/x"));
        assert_eq!(answered(&table, "/h/y"), None);
    }

    #[test]
    fn parents_makes_the_directory_a_path_is_in() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("a/b/file");
        parents(path.to_str().unwrap()).unwrap();
        assert!(tmp.path().join("a/b").is_dir());
    }

    #[test]
    fn parents_says_why_it_cannot_make_a_directory() {
        let tmp = tempfile::tempdir().unwrap();
        let blocker = tmp.path().join("file");
        fs::write(&blocker, "").unwrap();
        assert!(parents(blocker.join("below/x").to_str().unwrap()).is_err());
    }
}
