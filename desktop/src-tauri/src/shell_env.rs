//! The environment `hmz web` is started in: the one a login shell gives this account. An app
//! opened from the Finder is handed launchd's bare `PATH`, which misses the directories a
//! shell profile adds -- where `hmz` is, and node, nvm or volta, and the coding agents the
//! daemon `hmz web` forks goes on to run.

use std::collections::HashMap;
use std::env;
use std::ffi::{OsStr, OsString};
use std::io::Read;
use std::os::unix::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

pub type Env = HashMap<OsString, OsString>;

/// How long a login shell may take to say its environment: a profile that hangs or asks
/// something must not keep the app from starting.
const TIMEOUT: Duration = Duration::from_secs(5);

/// Written either side of the environment, so a profile that prints something is not read
/// as part of it.
const MARK: &str = "__HMZ_ENV__";

/// What a shell sets about itself, which is no child's: the directory it was in, how deep it
/// is, and the last command it ran.
const OWN: [&str; 4] = ["PWD", "OLDPWD", "SHLVL", "_"];

/// The login shell's environment, or this process's where it does not answer in time, with
/// the directories `hmz` is installed to put after `PATH`.
pub fn login() -> Env {
    let mut env = captured().unwrap_or_else(|| {
        log::warn!("the login shell did not say its environment; using the app's own");
        env::vars_os().collect()
    });
    for own in OWN {
        env.remove(OsStr::new(own));
    }
    let home = home(&env);
    let path = with_fallbacks(
        env.get(OsStr::new("PATH")).map(OsString::as_os_str),
        &home,
        env.get(OsStr::new("UV_TOOL_BIN_DIR"))
            .map(OsString::as_os_str),
    );
    env.insert("PATH".into(), path);
    env
}

/// This account's home directory.
pub fn home(env: &Env) -> PathBuf {
    env.get(OsStr::new("HOME"))
        .map(PathBuf::from)
        .or_else(env::home_dir)
        .unwrap_or_else(|| "/".into())
}

/// `$SHELL -ilc`, answering its environment between two marks.
fn captured() -> Option<Env> {
    let shell = env::var_os("SHELL")
        .filter(|shell| !shell.is_empty())
        .unwrap_or_else(|| "/bin/zsh".into());
    let script = format!("printf %s {MARK}; command env -0; printf %s {MARK}");
    let mut child = Command::new(shell)
        .args([OsStr::new("-ilc"), OsStr::new(&script)])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let mut stdout = child.stdout.take()?;
    let (sent, said) = mpsc::channel();
    // Read until the closing mark rather than to the end: something the profile started in
    // the background may hold the pipe open long after the shell is gone.
    thread::spawn(move || {
        let mut out = Vec::new();
        let mut chunk = [0; 8192];
        while let Ok(n @ 1..) = stdout.read(&mut chunk) {
            out.extend_from_slice(&chunk[..n]);
            if between(&out).is_some() {
                break;
            }
        }
        let _ = sent.send(out);
    });
    let out = said.recv_timeout(TIMEOUT).ok();
    // Gone or not, the shell is done with: killing one that exited is harmless, and the wait
    // reaps it either way.
    let _ = child.kill();
    let _ = child.wait();
    Some(parse(between(&out?)?))
}

/// What a shell printed between the two marks.
fn between(out: &[u8]) -> Option<&[u8]> {
    let mark = MARK.as_bytes();
    let start = out.windows(mark.len()).position(|w| w == mark)? + mark.len();
    let end = out[start..].windows(mark.len()).position(|w| w == mark)?;
    Some(&out[start..start + end])
}

/// `env -0`'s output: `NAME=value` entries, each ended by a NUL, where a value may hold
/// anything but a NUL -- a newline included.
fn parse(out: &[u8]) -> Env {
    out.split(|&b| b == 0)
        .filter_map(|entry| {
            let eq = entry.iter().position(|&b| b == b'=').filter(|&eq| eq > 0)?;
            Some((
                OsString::from_vec(entry[..eq].to_vec()),
                OsString::from_vec(entry[eq + 1..].to_vec()),
            ))
        })
        .collect()
}

/// `PATH`, then where `uv tool install` and Homebrew put programs, for whichever of them it
/// does not already name.
fn with_fallbacks(path: Option<&OsStr>, home: &Path, uv_tool_bin_dir: Option<&OsStr>) -> OsString {
    let mut dirs: Vec<PathBuf> = path
        .map(|p| env::split_paths(p).collect())
        .unwrap_or_default();
    let fallbacks = [
        Some(home.join(".local/bin")),
        uv_tool_bin_dir.filter(|d| !d.is_empty()).map(PathBuf::from),
        Some("/opt/homebrew/bin".into()),
        Some("/usr/local/bin".into()),
        Some("/usr/bin".into()),
        Some("/bin".into()),
    ];
    for dir in fallbacks.into_iter().flatten() {
        if !dirs.contains(&dir) {
            dirs.push(dir);
        }
    }
    // No directory can hold the separator, so joining cannot fail.
    env::join_paths(dirs).unwrap_or_else(|_| path.unwrap_or_default().to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::ffi::OsStrExt;

    #[test]
    fn parses_nul_separated_entries() {
        let env = parse(b"A=1\0MULTI=one\ntwo\0EQ=a=b\0EMPTY=\0=bad\0noequals\0");
        assert_eq!(env.len(), 4);
        assert_eq!(env[OsStr::new("A")], "1");
        assert_eq!(env[OsStr::new("MULTI")], "one\ntwo");
        assert_eq!(env[OsStr::new("EQ")], "a=b");
        assert_eq!(env[OsStr::new("EMPTY")], "");
    }

    #[test]
    fn reads_between_the_marks_alone() {
        let out = format!("Welcome!\n{MARK}PATH=/bin\0{MARK}bye");
        assert_eq!(between(out.as_bytes()), Some(&b"PATH=/bin\0"[..]));
        assert_eq!(between(format!("{MARK}PATH=/bin").as_bytes()), None);
    }

    #[test]
    fn falls_back_after_path_without_repeating_it() {
        let path = with_fallbacks(
            Some(OsStr::new("/custom:/opt/homebrew/bin")),
            Path::new("/Users/a"),
            Some(OsStr::new("/uv/bin")),
        );
        assert_eq!(
            path,
            "/custom:/opt/homebrew/bin:/Users/a/.local/bin:/uv/bin:/usr/local/bin:/usr/bin:/bin"
        );
        let bare = with_fallbacks(None, Path::new("/Users/a"), None);
        assert_eq!(
            bare,
            "/Users/a/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        );
    }

    #[test]
    fn captures_a_login_shell() {
        let env = captured().expect("a login shell answers");
        assert!(env.contains_key(OsStr::new("PATH")));
        assert!(env.contains_key(OsStr::new("HOME")));
    }

    #[test]
    fn login_drops_what_is_the_shells_own() {
        let env = login();
        assert!(!env.contains_key(OsStr::new("PWD")));
        let path = env[OsStr::new("PATH")].as_bytes();
        assert!(
            path.windows(b"/usr/local/bin".len())
                .any(|w| w == b"/usr/local/bin")
        );
    }
}
