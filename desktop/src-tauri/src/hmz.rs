//! Finding an `hmz` where nothing installs one: the one `HUMANIZE_HMZ` names, or the first on
//! `PATH` -- on this Mac for `stdio:local`, and in WSL on Windows for a development build.

use std::ffi::OsStr;
#[cfg(unix)]
use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
#[cfg(windows)]
use std::process::Stdio;

use crate::shell_env::Env;

/// Names the `hmz` to run, ahead of everything else (Section 3.4.12 of [DESKTOP]).
pub const OVERRIDE: &str = "HUMANIZE_HMZ";

/// The `hmz` `HUMANIZE_HMZ` names, or the first on `PATH`. On Windows, a Linux path in WSL.
pub fn find(env: &Env) -> Option<PathBuf> {
    first(candidates(env))
}

fn candidates(env: &Env) -> Vec<PathBuf> {
    if let Some(named) = env
        .get(OsStr::new(OVERRIDE))
        .filter(|named| !named.is_empty())
    {
        return vec![named.into()];
    }
    env.get(OsStr::new("PATH"))
        .map(|path| on(path))
        .unwrap_or_default()
}

/// `hmz` in each absolute directory of `path`.
#[cfg(unix)]
fn on(path: &OsStr) -> Vec<PathBuf> {
    std::env::split_paths(path)
        .filter(|dir| dir.is_absolute())
        .map(|dir| dir.join("hmz"))
        .collect()
}

/// `hmz` in each absolute directory of WSL's `path`, whose Linux paths only `/` joins.
#[cfg(windows)]
fn on(path: &OsStr) -> Vec<PathBuf> {
    path.to_string_lossy()
        .split(':')
        .filter(|dir| dir.starts_with('/'))
        .map(|dir| format!("{}/hmz", dir.trim_end_matches('/')).into())
        .collect()
}

#[cfg(unix)]
fn first(paths: Vec<PathBuf>) -> Option<PathBuf> {
    paths.into_iter().find(|path| runnable(path))
}

#[cfg(unix)]
pub fn runnable(path: &Path) -> bool {
    fs::metadata(path).is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
}

/// The first of `paths` WSL can run, asked of it once for them all.
#[cfg(windows)]
fn first(paths: Vec<PathBuf>) -> Option<PathBuf> {
    let script = r#"for p; do [ -f "$p" ] && [ -x "$p" ] && { printf %s "$p"; exit; }; done"#;
    let out = crate::wsl::command("/bin/sh", None)
        .args(["-c", script, "sh"])
        .args(&paths)
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .ok()
        .filter(|out| out.status.success())?;
    let found = String::from_utf8_lossy(&out.stdout).into_owned();
    (!found.is_empty()).then(|| found.into())
}

#[cfg(windows)]
pub fn runnable(path: &Path) -> bool {
    first(vec![path.into()]).is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn looks_where_it_is_told_then_along_path() {
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b".into()),
            (OVERRIDE.into(), "/named/hmz".into()),
        ]);
        assert_eq!(candidates(&env), [PathBuf::from("/named/hmz")]);
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b".into()),
            (OVERRIDE.into(), "".into()),
        ]);
        assert_eq!(
            candidates(&env),
            [PathBuf::from("/a/hmz"), PathBuf::from("/b/hmz")]
        );
        assert!(candidates(&Env::new()).is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn finds_the_first_runnable_hmz() {
        let dirs: Vec<_> = (0..3).map(|_| tempfile::tempdir().unwrap()).collect();
        fs::write(dirs[0].path().join("hmz"), "").unwrap();
        for dir in &dirs[1..] {
            let hmz = dir.path().join("hmz");
            fs::write(&hmz, "").unwrap();
            fs::set_permissions(&hmz, fs::Permissions::from_mode(0o755)).unwrap();
        }
        let path = std::env::join_paths(dirs.iter().map(|dir| dir.path())).unwrap();
        let env = Env::from([("PATH".into(), path)]);
        assert_eq!(find(&env), Some(dirs[1].path().join("hmz")));
    }
}
