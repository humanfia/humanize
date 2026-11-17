//! How both halves compare and translate paths, exactly as `proto.py` does.
//!
//! A Mac reaches `/etc`, `/tmp` and `/var` through `/private`, so that prefix is folded away
//! for everybody, Linux included: the machine that produced the other spelling is the one this
//! end cannot see. Case is folded only where the caller says the filesystem ignores it, with
//! full Unicode case folding (`ß` folds to `ss`), as Python's `str.casefold` does.

const ALIASED: [&str; 3] = ["etc", "tmp", "var"];

fn fold(text: &str) -> String {
    caseless::default_case_fold_str(text)
}

/// `path` without a leading `/private` where it names `/private/{etc,tmp,var}` as a whole
/// segment, and case-folded where `fold_case` says so.
pub fn path_key(path: &str, fold_case: bool) -> String {
    let folded = strip_private(path);
    if fold_case {
        fold(folded)
    } else {
        folded.to_owned()
    }
}

fn strip_private(path: &str) -> &str {
    let Some(rest) = path.strip_prefix("/private") else {
        return path;
    };
    for name in ALIASED {
        if let Some(after) = rest.strip_prefix('/').and_then(|r| r.strip_prefix(name))
            && (after.is_empty() || after.starts_with('/'))
        {
            return rest;
        }
    }
    path
}

/// Every name this exact directory answers to, the one it was given first.
pub fn path_spellings(path: &str) -> Vec<String> {
    let folded = path_key(path, false);
    if folded != path {
        return vec![path.to_owned(), folded];
    }
    let aliased = format!("/private{path}");
    if path_key(&aliased, false) != aliased {
        return vec![path.to_owned(), aliased];
    }
    vec![path.to_owned()]
}

/// Whether this directory, or anything under it, can be reached under a second name.
pub fn spelled_twice(path: &str) -> bool {
    let root = path.trim_end_matches('/');
    path_spellings(root).len() > 1
        || ALIASED
            .iter()
            .any(|name| format!("/private/{name}").starts_with(&format!("{root}/")))
}

/// The part of `path` below `root`, spelled as `path` spells it: `Some("")` when they name the
/// same directory, `None` when `path` is elsewhere. Lengths are measured in characters before
/// folding, so a root whose fold changes its length does not match (a refusal, not a guess).
pub fn path_within(path: &str, root: &str, fold_case: bool) -> Option<String> {
    let below = path_key(path, false);
    let above_key = path_key(root, false);
    let above = above_key.trim_end_matches('/');
    if above.is_empty() {
        return Some(below.trim_start_matches('/').to_owned());
    }
    let count = above.chars().count();
    let cut = below
        .char_indices()
        .nth(count)
        .map_or(below.len(), |(i, _)| i);
    let (head, tail) = below.split_at(cut);
    let same = if fold_case {
        fold(head) == fold(above)
    } else {
        head == above
    };
    if !same {
        return None;
    }
    if tail.is_empty() {
        return Some(String::new());
    }
    tail.starts_with('/')
        .then(|| tail.trim_start_matches('/').to_owned())
}

/// Whether `c` may stand on either side of a path in text: white space or one of
/// `'"=:,;()[]<>|&`, as the boundary class of `proto.py`'s pattern.
fn is_boundary(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c) || "'\"=:,;()[]<>|&".contains(c)
}

/// Replaces `prefix` with `replacement` wherever it names a path: preceded by the start of the
/// text or a boundary character, and followed by `/`, a boundary character or the end.
/// `insensitive` compares characters case-insensitively, for a target whose filesystem is.
pub fn rewrite_path_prefix(
    text: &str,
    prefix: &str,
    replacement: &str,
    insensitive: bool,
) -> String {
    if prefix == replacement || prefix.is_empty() || (!insensitive && !text.contains(prefix)) {
        return text.to_owned();
    }
    let chars: Vec<(usize, char)> = text.char_indices().collect();
    let wanted: Vec<char> = prefix.chars().collect();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < chars.len() {
        let starts = i == 0 || is_boundary(chars[i - 1].1);
        let fits = starts
            && i + wanted.len() <= chars.len()
            && wanted
                .iter()
                .zip(&chars[i..])
                .all(|(w, (_, c))| same_char(*w, *c, insensitive));
        let ends = fits
            && chars
                .get(i + wanted.len())
                .is_none_or(|(_, c)| *c == '/' || is_boundary(*c));
        if ends {
            out.push_str(replacement);
            i += wanted.len();
        } else {
            out.push(chars[i].1);
            i += 1;
        }
    }
    out
}

fn same_char(a: char, b: char, insensitive: bool) -> bool {
    a == b || (insensitive && a.to_lowercase().eq(b.to_lowercase()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn private_is_folded_as_whole_segments() {
        assert_eq!(path_key("/private/tmp/x", false), "/tmp/x");
        assert_eq!(path_key("/private/var", false), "/var");
        assert_eq!(path_key("/private/various", false), "/private/various");
        assert_eq!(path_key("/PRIVATE/tmp", false), "/PRIVATE/tmp");
        assert_eq!(path_key("/Users/Me", true), "/users/me");
    }

    #[test]
    fn spellings() {
        assert_eq!(path_spellings("/tmp/a"), ["/tmp/a", "/private/tmp/a"]);
        assert_eq!(path_spellings("/private/etc"), ["/private/etc", "/etc"]);
        assert_eq!(path_spellings("/home/a"), ["/home/a"]);
        assert!(spelled_twice("/"));
        assert!(spelled_twice("/tmp"));
        assert!(!spelled_twice("/home/a"));
    }

    #[test]
    fn within() {
        assert_eq!(path_within("/w/a/b", "/w", false).as_deref(), Some("a/b"));
        assert_eq!(path_within("/w", "/w/", false).as_deref(), Some(""));
        assert_eq!(path_within("/wide", "/w", false), None);
        assert_eq!(path_within("/W/A", "/w", true).as_deref(), Some("A"));
        assert_eq!(path_within("/W/A", "/w", false), None);
        assert_eq!(path_within("/x/y", "/", false).as_deref(), Some("x/y"));
        assert_eq!(
            path_within("/private/tmp/q", "/tmp", false).as_deref(),
            Some("q")
        );
    }

    #[test]
    fn rewrites_on_boundaries_only() {
        assert_eq!(
            rewrite_path_prefix("cat /w/f", "/w", "/r", false),
            "cat /r/f"
        );
        assert_eq!(
            rewrite_path_prefix("echo hello/world", "/w", "/r", false),
            "echo hello/world"
        );
        assert_eq!(
            rewrite_path_prefix("--flag=/wide", "/w", "/r", false),
            "--flag=/wide"
        );
        assert_eq!(
            rewrite_path_prefix("--flag=/w", "/w", "/r", false),
            "--flag=/r"
        );
        assert_eq!(rewrite_path_prefix("/w:/w/x", "/w", "/r", false), "/r:/r/x");
        assert_eq!(rewrite_path_prefix("cd /W/x", "/w", "/r", true), "cd /r/x");
        assert_eq!(rewrite_path_prefix("cd /W/x", "/w", "/r", false), "cd /W/x");
    }
}
