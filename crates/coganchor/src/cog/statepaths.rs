//! Which files belong to the agent rather than to the project. Port of
//! `hmz.coganchor.statepaths`. [Unit 8]
//!
//! An agent's own runtime and state directory live on this machine and must keep working
//! here: rerouting `~/.codex` to the target would lose the session, and rerouting one of the
//! agent's runtime executables would make it impossible to start or use its tools.
//! Everything else the agent touches belongs to the target.
//!
//! Also home to the `os.path` semantics the port needs to match Python's exactly
//! ([`normpath`], [`abspath`], [`expanduser`], [`realpath`], [`which`]), which the router
//! normalises its settings with too.

use std::borrow::Cow;
use std::ffi::{CString, OsString};
use std::fs;
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};

/// What coganchor knows about one coding agent (`statepaths.AgentProfile`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AgentProfile {
    /// Borrowed for a known agent; a generic profile is named for the program's basename.
    pub name: Cow<'static, str>,
    /// Paths holding the agent's own state, under `~`; always served from this machine.
    pub state_paths: &'static [&'static str],
}

/// Every agent coganchor knows, one per backend (`statepaths.PROFILES`).
pub const PROFILES: &[AgentProfile] = &[
    AgentProfile {
        name: Cow::Borrowed("agy"),
        state_paths: &["~/.gemini"],
    },
    AgentProfile {
        name: Cow::Borrowed("claude"),
        state_paths: &[
            "~/.claude",
            "~/.claude.json",
            "~/.local/share/claude",
            "~/.cache/claude-cli-nodejs",
        ],
    },
    AgentProfile {
        name: Cow::Borrowed("codex"),
        state_paths: &["~/.codex"],
    },
    // Settings, rules and login under one directory; the versions of the CLI itself, which
    // it re-execs from, under another.
    AgentProfile {
        name: Cow::Borrowed("cursor-agent"),
        state_paths: &["~/.cursor", "~/.local/share/cursor-agent"],
    },
    AgentProfile {
        name: Cow::Borrowed("dsh"),
        state_paths: &["~/.dsh"],
    },
    AgentProfile {
        name: Cow::Borrowed("grok"),
        state_paths: &["~/.grok"],
    },
    AgentProfile {
        name: Cow::Borrowed("kimi"),
        state_paths: &["~/.kimi-code", "~/.kimi"],
    },
    AgentProfile {
        name: Cow::Borrowed("litellm"),
        state_paths: &["~/.local/state/humanize/litellm"],
    },
    AgentProfile {
        name: Cow::Borrowed("mcode"),
        state_paths: &["~/.minimax", "~/.mavis"],
    },
    AgentProfile {
        name: Cow::Borrowed("qwen"),
        state_paths: &["~/.qwen"],
    },
    AgentProfile {
        name: Cow::Borrowed("pi"),
        state_paths: &["~/.pi"],
    },
    AgentProfile {
        name: Cow::Borrowed("omp"),
        state_paths: &["~/.omp"],
    },
    // opencode and mimocode are one program under two names: install, settings, model
    // catalogue, sessions database, and the locks around refreshing the catalogue.
    AgentProfile {
        name: Cow::Borrowed("opencode"),
        state_paths: &[
            "~/.opencode",
            "~/.config/opencode",
            "~/.local/share/opencode",
            "~/.cache/opencode",
            "~/.local/state/opencode",
        ],
    },
    AgentProfile {
        name: Cow::Borrowed("mimo"),
        state_paths: &[
            "~/.mimocode",
            "~/.config/mimocode",
            "~/.local/share/mimocode",
            "~/.cache/mimocode",
            "~/.local/state/mimocode",
        ],
    },
];

/// Per-user state of *any* agent, never mirrored (`statepaths.COMMON_STATE_PATHS`):
/// Humanize's own configuration, data, state and cache where the XDG specification puts them
/// by default (the providers a turn may run as among them), and what its home was called
/// before. Wherever an [`XDG_HOMES`] variable moves one of the four, it is kept there too.
pub const COMMON_STATE_PATHS: &[&str] = &[
    "~/.hmz",
    "~/.humanize",
    "~/.cache/humanize",
    "~/.config/humanize",
    "~/.local/share/humanize",
    "~/.local/state/humanize",
];

/// The variables that move those four, each a directory Humanize's own is `humanize` in
/// (`statepaths._XDG_HOMES`).
pub const XDG_HOMES: &[&str] = &[
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
];

/// Where Codex's npm package keeps its native binary (`_CODEX_VENDOR_BIN`).
const CODEX_VENDOR_BIN: &str = "vendor/x86_64-unknown-linux-musl/bin";

/// The agent, found, with what of this machine it needs to keep.
#[derive(Clone, Debug)]
pub struct Resolved {
    /// The profile it was recognised by (a generic one, with no state, for an unknown agent).
    pub profile: AgentProfile,
    /// The real path of the program to execute.
    pub program: PathBuf,
    /// Its argv, `argv[0]` as found on `PATH`.
    pub argv: Vec<OsString>,
    /// Its state and runtime directories, which stay here (sorted, unique).
    pub state: Vec<String>,
    /// Programs of its own (interpreter, vendored binaries), which run here (sorted, unique).
    pub programs: Vec<String>,
}

/// The known profile for `name`, or a permissive generic one (`statepaths.profile_for`).
pub fn profile_for(name: &str) -> AgentProfile {
    let basename = basename(name);
    // The Python SDK launches this bundled executable directly rather than through `dsh`,
    // but it owns the same durable session state.
    let wanted = if basename.starts_with("dsh-jsonrpc-agent-") {
        "dsh"
    } else {
        basename
    };
    PROFILES
        .iter()
        .find(|one| one.name == wanted)
        .cloned()
        .unwrap_or_else(|| AgentProfile {
            name: Cow::Owned(basename.to_owned()),
            state_paths: &[],
        })
}

/// Finds `argv[0]` on `PATH` and what it keeps; `"X: not found on PATH"` (`NotFound`)
/// otherwise, and `InvalidInput` for no command at all. Port of `statepaths.resolve`.
pub fn resolve(argv: &[OsString]) -> io::Result<Resolved> {
    let Some(first) = argv.first() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "no agent command given",
        ));
    };
    let name = first.to_string_lossy().into_owned();
    let found = if name.contains('/') {
        Some(name.clone())
    } else {
        which(&name)
    };
    let exists = if name.contains('/') {
        Path::new(first).exists()
    } else {
        found.as_deref().is_some_and(|one| Path::new(one).exists())
    };
    let Some(found) = found.filter(|_| exists) else {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            format!("{name}: not found on PATH"),
        ));
    };
    let located = abspath(&found);
    let program = realpath(&located);

    let profile = profile_for(&name);
    let mut state: Vec<String> = profile
        .state_paths
        .iter()
        .chain(COMMON_STATE_PATHS)
        .map(|one| expand(one))
        .collect();
    // A relative value is ignored, as the XDG specification has it.
    state.extend(
        XDG_HOMES
            .iter()
            .filter_map(|one| env_string(one))
            .filter(|moved| moved.starts_with('/'))
            .map(|moved| normpath(&format!("{}/humanize", moved.trim_end_matches('/')))),
    );
    // Only the agent's own runtime stays here; work helpers such as ripgrep go to the
    // target. A program kept in its own state directory is its runtime (grok re-execs its
    // native binary from `~/.grok/bin`).
    let mut programs = vec![located, program.clone()];
    programs.extend(profile.state_paths.iter().map(|one| expand(one)));
    let shebang = shebang(&program);
    if let Some(first) = shebang.first() {
        programs.push(first.clone());
        programs.extend(interpreter(&shebang));
    }
    if profile.name == "codex" {
        programs.extend(codex_runtime_programs(&program, &shebang));
    }
    programs.extend(beside(&program));

    // A path is kept as it was given, bytes and all; a name is what `PATH` found it as.
    let mut argv_out = vec![if name.contains('/') {
        first.clone()
    } else {
        OsString::from(found)
    }];
    argv_out.extend(argv[1..].iter().cloned());
    state.retain(|one| !one.is_empty());
    state.sort();
    state.dedup();
    programs.retain(|one| !one.is_empty());
    programs.sort();
    programs.dedup();
    Ok(Resolved {
        profile,
        program: PathBuf::from(program),
        argv: argv_out,
        state,
        programs,
    })
}

/// `os.path.normpath(os.path.expanduser(path))` (`statepaths._expand`).
fn expand(path: &str) -> String {
    normpath(&expanduser(path))
}

/// The command a script's first line names as its interpreter, split on white space
/// (`statepaths._shebang`): at most 256 bytes of the first line are read.
fn shebang(program: &str) -> Vec<String> {
    let Some(bytes) = read_head(program) else {
        return Vec::new();
    };
    let line = match bytes.iter().position(|&b| b == b'\n') {
        Some(at) => &bytes[..=at],
        None => &bytes[..],
    };
    let Some(rest) = line.strip_prefix(b"#!") else {
        return Vec::new();
    };
    String::from_utf8_lossy(rest)
        .split_whitespace()
        .map(str::to_owned)
        .collect()
}

/// The first 256 bytes of a file (`handle.readline(256)` reads no further).
fn read_head(program: &str) -> Option<Vec<u8>> {
    use std::io::Read;
    let handle = fs::File::open(program).ok()?;
    let mut bytes = Vec::with_capacity(256);
    handle.take(256).read_to_end(&mut bytes).ok()?;
    Some(bytes)
}

/// Every path an `#!/usr/bin/env NAME` line could reach its interpreter at
/// (`statepaths._interpreter`).
///
/// `env` runs here and then searches `PATH`, one `execve` per directory; a candidate not
/// kept here would be sent to the target, where the name resolves and the agent itself ends
/// up running. So the whole search is claimed: a candidate kept here fails here with the
/// `ENOENT` that makes `env` try the next one. Nothing for a line naming the interpreter
/// directly, which is already kept by its own path.
fn interpreter(shebang: &[String]) -> Vec<String> {
    if shebang.is_empty() || basename(&shebang[0]) != "env" {
        return Vec::new();
    }
    // `env -S "node --flag"` carries the whole command in one word, and `env NAME=VALUE
    // prog` sets variables before naming one.
    let name = shebang[1..]
        .iter()
        .flat_map(|word| word.split_whitespace())
        .find(|word| !word.starts_with('-') && !word.contains('='))
        .unwrap_or("");
    if name.is_empty() {
        return Vec::new();
    }
    if name.contains('/') {
        return vec![abspath(name), realpath(name)];
    }
    let path = env_string("PATH").unwrap_or_else(|| "/bin:/usr/bin".to_owned());
    let mut found: Vec<String> = path
        .split(':')
        .filter(|one| !one.is_empty())
        .map(|directory| join(directory, name))
        .collect();
    if let Some(resolved) = which(name) {
        found.push(abspath(&resolved));
        found.push(realpath(&resolved));
    }
    found
}

/// The programs an npm package keeps in the directory its agent's own program is in
/// (`statepaths._beside`): every executable file there, where that directory is inside a
/// package under `node_modules` (not the `.bin` every package puts its commands in). A
/// launcher hands over to a native binary beside it, and that binary is the agent.
fn beside(program: &str) -> Vec<String> {
    let directory = dirname(program);
    let parts: Vec<&str> = directory.split('/').collect();
    let Some(last) = parts.iter().rposition(|one| *one == "node_modules") else {
        return Vec::new();
    };
    let within = &parts[last + 1..];
    if within.is_empty() || within[0] == ".bin" {
        return Vec::new();
    }
    let Ok(entries) = fs::read_dir(directory) else {
        return Vec::new();
    };
    entries
        .filter_map(Result::ok)
        .map(|entry| join(directory, &entry.file_name().to_string_lossy()))
        .filter(|one| is_file(one) && access(one, libc::X_OK))
        .collect()
}

/// The Node, native CLI and code-mode host that implement Codex
/// (`statepaths._codex_runtime_programs`).
fn codex_runtime_programs(program: &str, shebang: &[String]) -> Vec<String> {
    let mut programs = Vec::new();
    if let Some(node) = shebang.iter().find(|part| basename(part) == "node") {
        let found = if node.contains('/') {
            Some(node.clone())
        } else {
            which(node)
        };
        if let Some(found) = found.filter(|one| Path::new(one).exists()) {
            programs.push(abspath(&found));
            programs.push(realpath(&found));
        }
    }
    let package = dirname(dirname(program));
    let candidates = [
        program.to_owned(),
        join(&join(package, CODEX_VENDOR_BIN), "codex"),
        join(
            &join(package, "node_modules/@openai/codex-linux-x64"),
            &join(CODEX_VENDOR_BIN, "codex"),
        ),
        join(
            &join(dirname(package), "codex-linux-x64"),
            &join(CODEX_VENDOR_BIN, "codex"),
        ),
    ];
    for candidate in candidates {
        if basename(&candidate) != "codex" || !is_file(&candidate) {
            continue;
        }
        let native = realpath(&candidate);
        programs.push(abspath(&candidate));
        programs.push(native.clone());
        let mut directories = vec![dirname(&candidate).to_owned()];
        if dirname(&native) != directories[0] {
            directories.push(dirname(&native).to_owned());
        }
        for directory in directories {
            let host = join(&directory, "codex-code-mode-host");
            if is_file(&host) {
                programs.push(abspath(&host));
                programs.push(realpath(&host));
            }
        }
    }
    programs
}

// ------------------------------------------------------------------- os.path, as Python has it

/// `os.path.basename`.
pub(crate) fn basename(path: &str) -> &str {
    path.rsplit('/').next().unwrap_or(path)
}

/// `os.path.dirname`: everything before the last `/`, its trailing slashes dropped unless
/// that is all there is.
pub(crate) fn dirname(path: &str) -> &str {
    let Some(at) = path.rfind('/') else {
        return "";
    };
    let head = &path[..=at];
    if head.chars().all(|c| c == '/') {
        head
    } else {
        head.trim_end_matches('/')
    }
}

/// `posixpath.join(a, b)` for two parts.
pub(crate) fn join(a: &str, b: &str) -> String {
    if b.starts_with('/') {
        b.to_owned()
    } else if a.is_empty() || a.ends_with('/') {
        format!("{a}{b}")
    } else {
        format!("{a}/{b}")
    }
}

/// `posixpath.normpath`: lexical, `..` popping a name, a leading `//` kept as POSIX allows.
pub fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".to_owned();
    }
    let slashes = if path.starts_with("//") && !path.starts_with("///") {
        2
    } else if path.starts_with('/') {
        1
    } else {
        0
    };
    let mut kept: Vec<&str> = Vec::new();
    for one in path.split('/') {
        if one.is_empty() || one == "." {
            continue;
        }
        if one != ".." || (slashes == 0 && kept.is_empty()) || kept.last() == Some(&"..") {
            kept.push(one);
        } else if !kept.is_empty() {
            kept.pop();
        }
    }
    let joined = format!("{}{}", "/".repeat(slashes), kept.join("/"));
    if joined.is_empty() {
        ".".to_owned()
    } else {
        joined
    }
}

/// A variable as Python's `os.environ` has it: set is set, whatever its bytes (a value
/// that is not UTF-8 is carried lossily, every path here being a string).
fn env_string(name: &str) -> Option<String> {
    std::env::var_os(name).map(|one| one.to_string_lossy().into_owned())
}

/// This process's working directory, as a string (`/` where it has none, which Python
/// would raise for instead).
fn getcwd() -> String {
    std::env::current_dir()
        .map(|one| one.to_string_lossy().into_owned())
        .unwrap_or_else(|_| "/".to_owned())
}

/// `os.path.abspath`: joined to the working directory where relative, then normalised.
pub fn abspath(path: &str) -> String {
    if path.starts_with('/') {
        normpath(path)
    } else {
        normpath(&join(&getcwd(), path))
    }
}

/// `os.path.expanduser`: a leading `~` or `~/` is `$HOME` (the password database's home
/// where it is unset); `~user` is that user's home; anything else is left alone.
pub fn expanduser(path: &str) -> String {
    let Some(rest) = path.strip_prefix('~') else {
        return path.to_owned();
    };
    let cut = rest.find('/').unwrap_or(rest.len());
    let (user, tail) = rest.split_at(cut);
    let home = if user.is_empty() {
        env_string("HOME").or_else(|| {
            nix::unistd::User::from_uid(nix::unistd::getuid())
                .ok()
                .flatten()
                .map(|one| one.dir.to_string_lossy().into_owned())
        })
    } else {
        nix::unistd::User::from_name(user)
            .ok()
            .flatten()
            .map(|one| one.dir.to_string_lossy().into_owned())
    };
    let Some(home) = home else {
        return path.to_owned();
    };
    let home = home.trim_end_matches('/');
    let joined = format!("{home}{tail}");
    if joined.is_empty() {
        "/".to_owned()
    } else {
        joined
    }
}

/// `os.path.realpath` (not strict): every symlink on the way followed, a name that is not
/// there kept as it was written, and a loop left where it was found -- `posixpath.realpath`
/// as Python 3.13 and later walk it.
pub fn realpath(path: &str) -> String {
    // The parts still to walk, last first; `None` marks a link resolved, the link itself
    // following it.
    let mut rest: Vec<Option<String>> = path
        .split('/')
        .rev()
        .map(|one| Some(one.to_owned()))
        .collect();
    let mut at = if path.starts_with('/') {
        "/".to_owned()
    } else {
        getcwd()
    };
    let mut seen: std::collections::HashMap<String, Option<String>> = Default::default();
    while let Some(name) = rest.pop() {
        let Some(name) = name else {
            if let Some(Some(link)) = rest.pop() {
                seen.insert(link, Some(at.clone()));
            }
            continue;
        };
        if name.is_empty() || name == "." {
            continue;
        }
        if name == ".." {
            let cut = at.rfind('/').unwrap_or(0);
            at.truncate(cut);
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
        let Ok(meta) = fs::symlink_metadata(&next) else {
            at = next;
            continue;
        };
        if !meta.file_type().is_symlink() {
            at = next;
            continue;
        }
        if let Some(known) = seen.get(&next) {
            // A link already resolved is its answer; one still being resolved is a loop.
            at = known.clone().unwrap_or(next);
            continue;
        }
        let Ok(target) = fs::read_link(&next) else {
            at = next;
            continue;
        };
        let target = target.to_string_lossy().into_owned();
        seen.insert(next.clone(), None);
        rest.push(Some(next));
        rest.push(None);
        if target.starts_with('/') {
            at = "/".to_owned();
        }
        rest.extend(target.split('/').rev().map(|one| Some(one.to_owned())));
    }
    at
}

/// Whether `path` is a regular file, through links (`os.path.isfile`).
fn is_file(path: &str) -> bool {
    fs::metadata(path).is_ok_and(|one| one.is_file())
}

/// `os.access(path, mode)`.
fn access(path: &str, mode: libc::c_int) -> bool {
    let Ok(path) = CString::new(Path::new(path).as_os_str().as_bytes()) else {
        return false;
    };
    // SAFETY: a valid NUL-terminated string, read only.
    unsafe { libc::access(path.as_ptr(), mode) == 0 }
}

/// `shutil.which(name)`: the first `dir/name` on `PATH` that exists, is executable and is
/// not a directory, as joined (not made absolute). `PATH` unset is the system's default
/// search path; `PATH` empty finds nothing; an empty entry is the working directory.
pub fn which(name: &str) -> Option<String> {
    let (directory, file) = match name.rfind('/') {
        Some(at) => (Some(dirname(name).to_owned()), &name[at + 1..]),
        None => (None, name),
    };
    let directories: Vec<String> = match directory.filter(|one| !one.is_empty()) {
        Some(one) => vec![one],
        None => {
            let path = env_string("PATH").unwrap_or_else(default_path);
            if path.is_empty() {
                return None;
            }
            path.split(':').map(str::to_owned).collect()
        }
    };
    let mut seen = std::collections::HashSet::new();
    for directory in directories {
        if !seen.insert(directory.clone()) {
            continue;
        }
        let candidate = join(&directory, file);
        // `shutil._access_check`: exists, executable, and not a directory.
        let usable = fs::metadata(&candidate).is_ok_and(|one| !one.is_dir())
            && access(&candidate, libc::F_OK | libc::X_OK);
        if usable {
            return Some(candidate);
        }
    }
    None
}

/// `os.confstr("CS_PATH")`, or `os.defpath` where the system has none.
fn default_path() -> String {
    // SAFETY: a null buffer of length 0 asks only for the length, NUL included.
    let length = unsafe { libc::confstr(libc::_CS_PATH, std::ptr::null_mut(), 0) };
    if length == 0 {
        return "/bin:/usr/bin".to_owned();
    }
    let mut buffer = vec![0u8; length];
    // SAFETY: the buffer is as long as said; confstr writes at most that, NUL included.
    let length = unsafe { libc::confstr(libc::_CS_PATH, buffer.as_mut_ptr().cast(), buffer.len()) };
    if length == 0 || length > buffer.len() {
        return "/bin:/usr/bin".to_owned();
    }
    buffer.truncate(length - 1);
    String::from_utf8(buffer).unwrap_or_else(|_| "/bin:/usr/bin".to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Expected values printed by `posixpath` itself (Python 3.14).
    #[test]
    fn os_path_answers_as_python_does() {
        for (path, normal) in [
            ("", "."),
            ("/", "/"),
            ("//", "//"),
            ("///a//b/", "/a/b"),
            ("a/../..", ".."),
            ("/../a", "/a"),
            ("//a/./b/../c", "//a/c"),
            ("a/b/..", "a"),
            ("../../x", "../../x"),
            ("/a/b/../../..", "/"),
        ] {
            assert_eq!(normpath(path), normal, "{path:?}");
        }
        for (path, dir, base) in [
            ("/a/b", "/a", "b"),
            ("/a/b/", "/a/b", ""),
            ("a", "", "a"),
            ("/", "/", ""),
            ("//x", "//", "x"),
            ("a/", "a", ""),
            ("///", "///", ""),
        ] {
            assert_eq!(dirname(path), dir, "{path:?}");
            assert_eq!(basename(path), base, "{path:?}");
        }
    }

    /// As `os.path.realpath` answered over the same tree.
    #[test]
    fn realpath_follows_links_and_keeps_what_is_not_there() {
        let tmp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(tmp.path()).unwrap();
        let root = root.to_str().unwrap();
        fs::create_dir(format!("{root}/real")).unwrap();
        std::os::unix::fs::symlink("real", format!("{root}/link")).unwrap();
        std::os::unix::fs::symlink("loop", format!("{root}/loop")).unwrap();
        assert_eq!(
            realpath(&format!("{root}/link/x/../y")),
            format!("{root}/real/y")
        );
        assert_eq!(realpath(&format!("{root}/link/..")), root);
        assert_eq!(
            realpath(&format!("{root}/loop/a")),
            format!("{root}/loop/a")
        );
    }
}
