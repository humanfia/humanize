//! Seatbelt: macOS's sandbox. Port of `hmz.coganchor.darwin.seatbelt` and the macOS branch
//! of `hmz.coganchor.fence.wrap`. [Unit 5]
//!
//! The profile is built on every platform (so it can be tested anywhere); only a Mac runs it.
//!
//! A profile names what may be read, what may be written and, where the network is cut, the
//! one TCP port on loopback that may still be connected to; [`command`] is the command line
//! that runs a program inside it: `sandbox-exec`, which applies the profile to itself and then
//! becomes the program. `sandbox-exec` rather than `sandbox_init` in a forked child, since the
//! process forking serves a proxy from threads of its own, and a child of a threaded process
//! may take no lock one of them held, which compiling a profile takes.
//!
//! Paths are named as the kernel resolves them: `/tmp` is `/private/tmp` to Seatbelt. A path
//! read is granted as given and as it resolves; a path written as given only -- it is what the
//! fence reached, every link on the way already followed, and resolved again here it would
//! follow a link put there since. Nor may a link be put at one, nor a directory written be
//! taken from its name. Metadata is readable everywhere, as is `/` itself.
//!
//! Where the network is cut the profile says only as near as Seatbelt can: a host is
//! `localhost` or `*`, and a Mach service that reaches the network for whoever asks is a way
//! out no rule on this process's own sockets closes.

use std::collections::{HashMap, HashSet};
use std::ffi::OsString;
use std::path::Path;

use crate::fence::{Able, Fence};

/// The command a profile is applied with (`SANDBOX_EXEC`).
pub const SANDBOX_EXEC: &str = "/usr/bin/sandbox-exec";

/// The pseudo-terminals a program may write to however little else: the slave side of the
/// terminal it was started on, which a Mac numbers in `/dev` (`_TERMINALS`).
const TERMINALS: &str = r"^/dev/ttys[0-9]+$";

/// The system resolver's socket, shut where the network is cut: a name asked for is a name the
/// resolver sends out (`_RESOLVER`).
const RESOLVER: &str = "/private/var/run/mDNSResponder";

/// `_CS_DARWIN_USER_CACHE_DIR`, the `confstr` name of the per-user cache directory.
const DARWIN_USER_CACHE_DIR: i32 = 65538;

/// The profile text and its `-D` parameters for `fence`, with the loopback proxy `port` the
/// one outbound connection allowed where the network is cut.
///
/// Reads `fence.read`; writes `fence.write` and `fence.tmp` -- which the caller hands over as
/// the paths `Fence::ready` reached them at, links followed (`_seatbelted`'s `reached`) --
/// and, on a Mac, the per-user cache's `mds` directory, whose lock native TLS takes even to
/// read the keychains (`security`).
pub fn profile(fence: &Fence, port: Option<u16>) -> (String, Vec<(String, String)>) {
    let mut write = fence.write.clone();
    if !fence.tmp.is_empty() {
        write.push(fence.tmp.clone());
    }
    write.extend(security());
    rules(&fence.read, &write, port)
}

/// The profile for exactly these paths and port, and the parameters the paths are named by
/// (`Profile.rules`). Named by parameter rather than written into the profile, so that a path
/// holding a quote or a backslash is a path rather than the end of a string.
pub fn rules(
    read: &[String],
    write: &[String],
    port: Option<u16>,
) -> (String, Vec<(String, String)>) {
    let mut params = Vec::new();
    let mut named = |paths: &[String], prefix: &str, resolved: bool| -> Vec<String> {
        held(paths, resolved)
            .into_iter()
            .enumerate()
            .map(|(index, path)| {
                params.push((format!("{prefix}{index}"), path));
                format!("(param \"{prefix}{index}\")")
            })
            .collect()
    };
    let reading = named(read, "R", true);
    let writing = named(write, "W", false);
    let mut lines: Vec<String> = vec![
        "(version 1)".into(),
        "(allow default)".into(),
        "(deny file-read* file-write* process-exec)".into(),
        "(allow file-read-metadata)".into(),
        "(allow file-read-data (literal \"/\"))".into(),
    ];
    if !reading.is_empty() {
        let beneath = joined(&reading, "subpath");
        lines.push(format!("(allow file-read* process-exec {beneath})"));
    }
    if !writing.is_empty() {
        let beneath = joined(&writing, "subpath");
        let itself = joined(&writing, "literal");
        lines.push(format!(
            "(allow file-read* file-write* process-exec {beneath})"
        ));
        lines.push(format!(
            "(deny file-write-create (require-all (vnode-type SYMLINK) (require-any {itself})))"
        ));
        // A swap (`renamex_np`) is checked against what each name holds before it, so a
        // directory is never taken from its name, by a swap or otherwise.
        lines.push(format!(
            "(deny file-write-unlink (require-all (vnode-type DIRECTORY) (require-any {itself})))"
        ));
    }
    lines.push(format!(
        "(allow file-read* file-write* (regex #\"{TERMINALS}\"))"
    ));
    if let Some(port) = port {
        lines.push("(deny network*)".into());
        lines.push(format!(
            "(allow network-outbound (remote tcp \"localhost:{port}\"))"
        ));
        lines.push("(allow network-inbound (local tcp \"localhost:*\"))".into());
        lines.push("(allow network* (local unix-socket) (remote unix-socket))".into());
        lines.push(format!(
            "(deny network-outbound (remote unix-socket (path-literal \"{RESOLVER}\")))"
        ));
    }
    (lines.join("\n"), params)
}

fn joined(params: &[String], kind: &str) -> String {
    params
        .iter()
        .map(|one| format!("({kind} {one})"))
        .collect::<Vec<_>>()
        .join(" ")
}

/// Each path as given (normalised) and, where `resolved`, as the kernel resolves it, each
/// once, in order (`_held`).
fn held(paths: &[String], resolved: bool) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for path in paths {
        let mut ones = vec![normal(path)];
        if resolved {
            ones.push(realpath(path));
        }
        for one in ones {
            if seen.insert(one.clone()) {
                out.push(one);
            }
        }
    }
    out
}

/// A path normalised lexically, always absolute, as `os.sep + normpath(path).lstrip(os.sep)`.
fn normal(path: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    let absolute = path.starts_with('/');
    for name in path.split('/') {
        match name {
            "" | "." => {}
            ".." => {
                if parts.last().is_some_and(|last| *last != "..") {
                    parts.pop();
                } else if !absolute {
                    parts.push("..");
                }
            }
            name => parts.push(name),
        }
    }
    format!("/{}", parts.join("/"))
}

/// A path with every link resolved as far as it exists, as `os.path.realpath` (non-strict)
/// resolves it, step for step: a name that cannot be looked at is kept as written, and a link
/// met again while it is still being resolved -- a loop -- is kept as the link's own path.
pub fn realpath(path: &str) -> String {
    /// One part still to resolve, or the mark that the link before it has been.
    enum Part {
        Name(String),
        Resolved(String),
    }
    let mut rest: Vec<Part> = path
        .split('/')
        .rev()
        .map(|n| Part::Name(n.into()))
        .collect();
    let mut at = if path.starts_with('/') {
        "/".to_owned()
    } else {
        std::env::current_dir().map_or_else(|_| "/".to_owned(), |d| d.to_string_lossy().into())
    };
    let mut seen: HashMap<String, Option<String>> = HashMap::new();
    while let Some(part) = rest.pop() {
        let name = match part {
            Part::Resolved(link) => {
                seen.insert(link, Some(at.clone()));
                continue;
            }
            Part::Name(name) => name,
        };
        if name.is_empty() || name == "." {
            continue;
        }
        if name == ".." {
            at.truncate(at.rfind('/').unwrap_or(0));
            if at.is_empty() {
                at.push('/');
            }
            continue;
        }
        let next = if at == "/" {
            format!("/{name}")
        } else {
            format!("{at}/{name}")
        };
        match std::fs::symlink_metadata(&next) {
            Ok(meta) if meta.file_type().is_symlink() => {}
            _ => {
                at = next;
                continue;
            }
        }
        if let Some(known) = seen.get(&next) {
            // Resolved already, or a loop: kept as the link's own path.
            at = known.clone().unwrap_or(next);
            continue;
        }
        let Ok(target) = std::fs::read_link(&next) else {
            at = next;
            continue;
        };
        let target = target.to_string_lossy().into_owned();
        if target.starts_with('/') {
            at = "/".to_owned();
        }
        seen.insert(next.clone(), None);
        rest.push(Part::Resolved(next));
        rest.extend(target.split('/').rev().map(|n| Part::Name(n.into())));
    }
    at
}

/// The per-user cache's `mds` directory, as reached through every link above it, where it is
/// not itself a link (`_seatbelted`'s `security`). None off a Mac.
pub fn security() -> Option<String> {
    let cache = confstr(DARWIN_USER_CACHE_DIR)?;
    let mds = Path::new(&cache).join("mds");
    if mds.is_symlink() {
        return None;
    }
    Some(format!("{}/mds", realpath(&cache).trim_end_matches('/')))
}

#[cfg(target_os = "macos")]
fn confstr(name: i32) -> Option<String> {
    let size = unsafe { libc::confstr(name, std::ptr::null_mut(), 0) };
    if size == 0 {
        return None;
    }
    let mut buf = vec![0u8; size];
    // SAFETY: `buf` holds `size` bytes, which is what `confstr` was asked to fill.
    let wrote = unsafe { libc::confstr(name, buf.as_mut_ptr().cast(), size) };
    if wrote == 0 || wrote > size {
        return None;
    }
    let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
    let said = String::from_utf8(buf[..end].to_vec()).ok()?;
    (!said.is_empty()).then_some(said)
}

#[cfg(not(target_os = "macos"))]
fn confstr(_: i32) -> Option<String> {
    None
}

/// The `/usr/bin/sandbox-exec` command line running `argv` inside `fence`
/// (`Profile.command`): `sandbox-exec -DNAME=PATH ... -p PROFILE -- PROGRAM ARGS...`.
pub fn command(fence: &Fence, port: Option<u16>, argv: &[OsString]) -> Vec<OsString> {
    let (profile, params) = profile(fence, port);
    let mut line: Vec<OsString> = vec![SANDBOX_EXEC.into()];
    line.extend(
        params
            .into_iter()
            .map(|(name, value)| format!("-D{name}={value}").into()),
    );
    line.push("-p".into());
    line.push(profile.into());
    line.push("--".into());
    line.extend(argv.iter().cloned());
    line
}

/// Whether `sandbox-exec` works here, asked once (`available`): a process already inside a
/// sandbox cannot apply another, so it is run once with a profile allowing everything.
pub fn able() -> Able {
    let ok = available();
    Able { fs: ok, net: ok }
}

/// Whether a profile can be applied here at all, asked once and remembered.
pub fn available() -> bool {
    static AVAILABLE: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *AVAILABLE.get_or_init(probe)
}

#[cfg(target_os = "macos")]
fn probe() -> bool {
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};

    let Ok(mut child) = Command::new(SANDBOX_EXEC)
        .args(["-p", "(version 1)(allow default)", "/usr/bin/true"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    else {
        return false;
    };
    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return status.success(),
            Ok(None) if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(10));
            }
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return false;
            }
        }
    }
}

#[cfg(not(target_os = "macos"))]
fn probe() -> bool {
    false
}
