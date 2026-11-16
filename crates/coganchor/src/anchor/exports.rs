//! Translating the virtual paths a cog speaks into real paths here. Port of
//! `hmz.coganchor.serve.exports`. [Unit 1]
//!
//! A client addresses this machine with *virtual* paths, normally the very paths the agent it
//! traces believes it is using. An export maps a virtual prefix onto a real directory here,
//! which lets the workspace live somewhere other than where the client thinks it is. Every
//! request is resolved through the table, so the export list is also this machine's
//! authorisation boundary: a path no export holds is refused.
//!
//! A path is matched as this machine's own filesystem would read it: a Mac reaches `/var`,
//! `/tmp` and `/etc` through `/private`, and ignores case besides, so a request naming a
//! directory the way the other end learned to name it still lands on the file the export
//! opened. What that admits is an export's own directory under its other name, never one
//! outside it: the real path is always built by joining onto the export's real directory.

use std::path::PathBuf;

use serde_json::Value;

use crate::proto::json::{from_os, to_os};
use crate::proto::{RemoteError, path_key, path_spellings, path_within, rewrite_path_prefix};

/// One exported directory: what the client calls it, and where it is here.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Export {
    pub virtual_path: String,
    pub real: PathBuf,
}

impl Export {
    /// Reads `VIRTUAL:REAL`, or `PATH` for an export that is its own real directory.
    fn parse(spec: &str) -> Result<Export, String> {
        let (virtual_path, real) = spec.split_once(':').unwrap_or((spec, spec));
        if virtual_path.is_empty() || real.is_empty() {
            return Err(format!(
                "malformed export {}; expected VIRTUAL[:REAL]",
                py_repr(spec)
            ));
        }
        Ok(Export {
            virtual_path: normalise(virtual_path)?,
            real: PathBuf::from(abspath(&expanduser(real))),
        })
    }
}

/// Every export of a session, longest virtual path first; also this machine's authorisation
/// boundary, since a path no export holds is refused.
#[derive(Clone, Debug)]
pub struct ExportTable {
    exports: Vec<Export>,
    fold_case: bool,
}

impl ExportTable {
    /// Reads `--export VIRTUAL[:REAL]` specs (split at the first `:`), sorted longest
    /// `path_key(virtual)` first, stably. The message of the error is what `hmz: ` prefixes.
    pub fn parse(specs: &[String]) -> Result<ExportTable, String> {
        let exports = specs
            .iter()
            .map(|spec| Export::parse(spec))
            .collect::<Result<Vec<_>, _>>()?;
        Self::from_exports(exports, cfg!(target_os = "macos"))
    }

    /// A table of these exports, matched case-insensitively where `fold_case` says so.
    fn from_exports(mut exports: Vec<Export>, fold_case: bool) -> Result<ExportTable, String> {
        if exports.is_empty() {
            return Err("at least one export is required".into());
        }
        // Longest first, measured as prefixes are matched: an export written the long way
        // round (`/private/tmp/x` for `/tmp/x`) is no deeper for having been.
        exports
            .sort_by_key(|e| std::cmp::Reverse(path_key(&e.virtual_path, false).chars().count()));
        Ok(ExportTable { exports, fold_case })
    }

    /// The exports in the order the table holds them, which is the order `HELLO` lists them.
    pub fn exports(&self) -> &[Export] {
        &self.exports
    }

    /// Whether this machine's filesystem ignores case (a Mac's does).
    pub fn fold_case(&self) -> bool {
        self.fold_case
    }

    /// The real path a virtual one names; `EACCES` "path is outside every export" otherwise.
    ///
    /// `..` segments are collapsed before matching, so a request can never climb out of its
    /// export. A relative path is `EINVAL`.
    pub fn resolve(&self, virtual_path: &str) -> Result<PathBuf, RemoteError> {
        let path =
            normalise(virtual_path).map_err(|message| RemoteError::new(libc::EINVAL, message))?;
        for export in &self.exports {
            let Some(below) = path_within(&path, &export.virtual_path, self.fold_case) else {
                continue;
            };
            return Ok(if below.is_empty() {
                export.real.clone()
            } else {
                export.real.join(to_os(&below))
            });
        }
        Err(
            RemoteError::new(libc::EACCES, "path is outside every export")
                .with_filename(virtual_path),
        )
    }

    /// `text` with every export's virtual prefix (and its `/private` spelling) rewritten to
    /// its real one, export by export, as `ExportTable.rewrite` does.
    ///
    /// Commands run natively here and know nothing of the table, so an argument naming a
    /// virtual path is translated before the program starts.
    pub fn rewrite(&self, text: &str) -> String {
        let mut text = text.to_owned();
        for export in &self.exports {
            let real = from_os(export.real.as_os_str());
            for spelling in path_spellings(&export.virtual_path) {
                text = rewrite_path_prefix(&text, &spelling, &real, self.fold_case);
            }
        }
        text
    }

    /// The `exports` list of a `HELLO` reply: `[{"virtual": .., "real": ..}, ...]`.
    pub fn hello(&self) -> Value {
        Value::Array(
            self.exports
                .iter()
                .map(|e| {
                    serde_json::json!({
                        "virtual": e.virtual_path,
                        "real": from_os(e.real.as_os_str()),
                    })
                })
                .collect(),
        )
    }
}

/// A virtual path in its one spelling (`posixpath.normpath`), refused unless absolute.
pub(crate) fn normalise(path: &str) -> Result<String, String> {
    if !path.starts_with('/') {
        return Err(format!(
            "virtual paths must be absolute, got {}",
            py_repr(path)
        ));
    }
    Ok(normpath(path))
}

/// `posixpath.normpath`: `.` and empty segments dropped, `..` collapsed, and a leading `//`
/// (exactly two slashes) kept, as POSIX lets it mean something of its own.
pub(crate) fn normpath(path: &str) -> String {
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
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        if part.is_empty() || part == "." {
            continue;
        }
        if part != ".." || (initial == 0 && parts.is_empty()) || parts.last() == Some(&"..") {
            parts.push(part);
        } else if !parts.is_empty() {
            parts.pop();
        }
    }
    let joined = format!("{}{}", "/".repeat(initial), parts.join("/"));
    if joined.is_empty() {
        ".".into()
    } else {
        joined
    }
}

/// `os.path.expanduser`: a leading `~` or `~user` replaced by that home directory.
fn expanduser(path: &str) -> String {
    let Some(rest) = path.strip_prefix('~') else {
        return path.to_owned();
    };
    let cut = rest.find('/').unwrap_or(rest.len());
    let (user, tail) = rest.split_at(cut);
    let home = if user.is_empty() {
        match std::env::var("HOME") {
            Ok(home) => Some(home),
            Err(_) => nix::unistd::User::from_uid(nix::unistd::getuid())
                .ok()
                .flatten()
                .map(|u| u.dir.to_string_lossy().into_owned()),
        }
    } else {
        nix::unistd::User::from_name(user)
            .ok()
            .flatten()
            .map(|u| u.dir.to_string_lossy().into_owned())
    };
    let Some(home) = home else {
        return path.to_owned();
    };
    let joined = format!("{}{tail}", home.trim_end_matches('/'));
    if joined.is_empty() {
        "/".into()
    } else {
        joined
    }
}

/// `os.path.abspath`: joined onto the working directory where relative, then normalised.
fn abspath(path: &str) -> String {
    if path.starts_with('/') {
        return normpath(path);
    }
    let cwd = std::env::current_dir()
        .map(|d| from_os(d.as_os_str()))
        .unwrap_or_else(|_| "/".into());
    normpath(&format!("{}/{path}", cwd.trim_end_matches('/')))
}

/// A string as Python's `repr` writes it, for messages that quote what was typed.
pub(crate) fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(text.len() + 2);
    out.push(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c == '\x7f' => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn table(specs: &[&str], fold_case: bool) -> ExportTable {
        let exports = specs.iter().map(|s| Export::parse(s).unwrap()).collect();
        ExportTable::from_exports(exports, fold_case).unwrap()
    }

    #[test]
    fn normpath_as_python() {
        assert_eq!(normpath("/a/./b/../c/"), "/a/c");
        assert_eq!(normpath("//a//b"), "//a/b");
        assert_eq!(normpath("///a"), "/a");
        assert_eq!(normpath("/../.."), "/");
        assert_eq!(normpath("a/../../b"), "../b");
        assert_eq!(normpath(""), ".");
    }

    #[test]
    fn parses_specs() {
        let e = Export::parse("/w:/r/x/").unwrap();
        assert_eq!(e.virtual_path, "/w");
        assert_eq!(e.real, PathBuf::from("/r/x"));
        let same = Export::parse("/w/./a").unwrap();
        assert_eq!(same.real, PathBuf::from("/w/a"));
        assert_eq!(
            Export::parse("w:/r").unwrap_err(),
            "virtual paths must be absolute, got 'w'"
        );
        assert_eq!(
            Export::parse(":/r").unwrap_err(),
            "malformed export ':/r'; expected VIRTUAL[:REAL]"
        );
        let home = Export::parse("/h:~/x").unwrap();
        assert!(!home.real.to_string_lossy().contains('~'));
        assert!(Export::parse("/rel:rel").unwrap().real.is_absolute());
    }

    #[test]
    fn longest_first_stably() {
        let t = table(&["/a:/1", "/a/b:/2", "/private/tmp:/3", "/c:/4"], false);
        let order: Vec<_> = t
            .exports()
            .iter()
            .map(|e| e.virtual_path.as_str())
            .collect();
        // `/private/tmp` is measured as `/tmp`, no longer than `/a/b`, which came first.
        assert_eq!(order, ["/a/b", "/private/tmp", "/a", "/c"]);
    }

    #[test]
    fn resolves() {
        let t = table(&["/w:/r", "/w/deep:/d"], false);
        assert_eq!(t.resolve("/w").unwrap(), PathBuf::from("/r"));
        assert_eq!(t.resolve("/w/x/../y").unwrap(), PathBuf::from("/r/y"));
        assert_eq!(t.resolve("/w/deep/z").unwrap(), PathBuf::from("/d/z"));
        let out = t.resolve("/w/../etc").unwrap_err();
        assert_eq!(out.errno, libc::EACCES);
        assert_eq!(out.strerror, "path is outside every export");
        assert_eq!(out.filename.as_deref(), Some("/w/../etc"));
        assert_eq!(t.resolve("w").unwrap_err().errno, libc::EINVAL);
        let folded = table(&["/W:/r"], true);
        assert_eq!(folded.resolve("/w/A").unwrap(), PathBuf::from("/r/A"));
        let private = table(&["/tmp/x:/r"], false);
        assert_eq!(
            private.resolve("/private/tmp/x/f").unwrap(),
            PathBuf::from("/r/f")
        );
    }

    #[test]
    fn rewrites_every_spelling() {
        let t = table(&["/tmp/w:/real"], false);
        assert_eq!(
            t.rewrite("cat /tmp/w/a /private/tmp/w/b"),
            "cat /real/a /real/b"
        );
        assert_eq!(t.rewrite("echo /tmp/wide"), "echo /tmp/wide");
    }

    #[test]
    fn hello_lists_in_order() {
        let t = table(&["/a:/1", "/a/b:/2"], false);
        assert_eq!(
            t.hello(),
            serde_json::json!([{"virtual": "/a/b", "real": "/2"}, {"virtual": "/a", "real": "/1"}])
        );
    }

    #[test]
    fn repr_as_python() {
        assert_eq!(py_repr("a'b"), "\"a'b\"");
        assert_eq!(py_repr("a\\b\n"), "'a\\\\b\\n'");
    }
}
