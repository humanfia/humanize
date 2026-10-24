//! The environment `hmz web` is started in: the one a login shell gives this account. An app
//! opened from the Finder is handed launchd's bare `PATH`, which misses the directories a
//! shell profile adds -- where `hmz` is, and node, nvm or volta, and the coding agents the
//! daemon `hmz web` forks goes on to run. On Windows, where hmz lives in WSL, it is the one a
//! login shell gives this account there.

use std::collections::HashMap;
use std::env;
use std::ffi::{OsStr, OsString};
use std::io::Read;
#[cfg(unix)]
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
/// the directories `hmz` is installed to put after `PATH`. On Windows, WSL's own stands in for
/// this process's.
pub fn login() -> Env {
    let mut env = captured().unwrap_or_else(|| {
        log::warn!("the login shell did not say its environment; using the app's own");
        own()
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
    // WSL is not handed this process's environment, so the hmz named in Windows is carried in.
    #[cfg(windows)]
    if let Some(named) = env::var_os(crate::server::OVERRIDE) {
        env.insert(crate::server::OVERRIDE.into(), named);
    }
    env
}

/// This account's home directory; on Windows, its home in WSL.
pub fn home(env: &Env) -> PathBuf {
    let home = env.get(OsStr::new("HOME")).map(PathBuf::from);
    #[cfg(unix)]
    let home = home.or_else(env::home_dir);
    home.unwrap_or_else(|| "/".into())
}

/// What a shell runs to answer its environment between two marks.
fn script() -> String {
    format!("printf %s {MARK}; command env -0; printf %s {MARK}")
}

/// `$SHELL -ilc`, answering its environment between two marks.
#[cfg(unix)]
fn captured() -> Option<Env> {
    let shell = env::var_os("SHELL")
        .filter(|shell| !shell.is_empty())
        .unwrap_or_else(|| "/bin/zsh".into());
    let mut command = Command::new(shell);
    command.args([OsStr::new("-ilc"), OsStr::new(&script())]);
    answered(command)
}

#[cfg(unix)]
fn own() -> Env {
    env::vars_os().collect()
}

/// `$SHELL -ilc` in WSL, where `wsl.exe` sets `SHELL` to the account's.
#[cfg(windows)]
fn captured() -> Option<Env> {
    let mut command = crate::wsl::command("/bin/sh", None);
    command.args(["-c", r#"exec "${SHELL:-/bin/sh}" -ilc "$0""#, &script()]);
    answered(command)
}

/// WSL's own environment, which no profile adds to; none where WSL does not answer either.
#[cfg(windows)]
fn own() -> Env {
    let mut command = crate::wsl::command("/bin/sh", None);
    command.args(["-c", &script()]);
    answered(command).unwrap_or_default()
}

/// The environment `command` answers between two marks, where it does so in time.
fn answered(mut command: Command) -> Option<Env> {
    let mut child = command
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
            Some((os(&entry[..eq]), os(&entry[eq + 1..])))
        })
        .collect()
}

#[cfg(unix)]
fn os(bytes: &[u8]) -> OsString {
    OsString::from_vec(bytes.to_vec())
}

/// WSL's bytes, which Windows holds only as text.
#[cfg(windows)]
fn os(bytes: &[u8]) -> OsString {
    String::from_utf8_lossy(bytes).into_owned().into()
}

/// `PATH`, then where `uv tool install` and Homebrew put programs, for whichever of them it
/// does not already name.
#[cfg(unix)]
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

/// WSL's `PATH`, then where `uv tool install` and Debian put programs, for whichever of them it
/// does not already name: Linux paths, joined as Linux joins them.
#[cfg(windows)]
fn with_fallbacks(path: Option<&OsStr>, home: &Path, uv_tool_bin_dir: Option<&OsStr>) -> OsString {
    let path = path.map(OsStr::to_string_lossy).unwrap_or_default();
    let mut dirs: Vec<String> = path
        .split(':')
        .filter(|dir| !dir.is_empty())
        .map(Into::into)
        .collect();
    let fallbacks = [
        Some(format!(
            "{}/.local/bin",
            home.to_string_lossy().trim_end_matches('/')
        )),
        uv_tool_bin_dir
            .filter(|d| !d.is_empty())
            .map(|d| d.to_string_lossy().into_owned()),
        Some("/usr/local/bin".into()),
        Some("/usr/bin".into()),
        Some("/bin".into()),
    ];
    for dir in fallbacks.into_iter().flatten() {
        if !dirs.contains(&dir) {
            dirs.push(dir);
        }
    }
    dirs.join(":").into()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
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

    #[cfg(unix)]
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

    #[cfg(windows)]
    #[test]
    fn falls_back_after_wsls_path_without_repeating_it() {
        let path = with_fallbacks(
            Some(OsStr::new("/custom:/mnt/c/Program Files/x::/usr/bin")),
            Path::new("/home/a"),
            Some(OsStr::new("/uv/bin")),
        );
        assert_eq!(
            path,
            "/custom:/mnt/c/Program Files/x:/usr/bin:/home/a/.local/bin:/uv/bin:/usr/local/bin:/bin"
        );
        let bare = with_fallbacks(None, Path::new("/"), None);
        assert_eq!(bare, "/.local/bin:/usr/local/bin:/usr/bin:/bin");
    }

    #[cfg(windows)]
    #[test]
    fn takes_wsls_home_as_it_is() {
        let env = Env::from([("HOME".into(), "/home/a".into())]);
        assert_eq!(home(&env).to_str(), Some("/home/a"));
        assert_eq!(home(&Env::new()).to_str(), Some("/"));
    }

    #[cfg(unix)]
    #[test]
    fn captures_a_login_shell() {
        let env = captured().expect("a login shell answers");
        assert!(env.contains_key(OsStr::new("PATH")));
        assert!(env.contains_key(OsStr::new("HOME")));
    }

    #[cfg(unix)]
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
