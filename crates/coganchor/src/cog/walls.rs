//! The fence around a supervised agent: Landlock plus, where the network is cut, the loopback
//! proxy. Port of `_Walls` in `hmz.coganchor.anchor` (anchor.py:792-882). [Unit 12]
//!
//! Here, the agent process itself: the fence as drawn on this machine, with the mirror granted
//! as the workspace is -- the mirror being the workspace, to a process whose every path into it
//! is rewritten into the mirror -- put up in the forked child by the supervisor, with the proxy
//! that is its one way out served by this process, outside the wall. There, every command the
//! agent runs: [`Walls::told`], the fence's levels, for the target to draw it again around its
//! own paths.

use std::ffi::OsString;
use std::io;
use std::os::unix::fs::DirBuilderExt;
use std::path::{Path, PathBuf};

use serde_json::{Value, json};

use crate::cog::config::{abspath, normpath};
use crate::fence::Fence;
use crate::fence::landlock::Ruleset;
use crate::fence::proxy::Proxy;

/// The variables every common HTTP client reads its proxy from (`wrap.PROXIES`).
pub const PROXIES: [&str; 6] = [
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
];

/// Where a build keeps its caches, and where when nothing says (`wrap.CACHES`): pointed into
/// the scratch where the fence would not let them be written.
pub const CACHES: [(&str, &str); 5] = [
    ("XDG_CACHE_HOME", "~/.cache"),
    ("UV_CACHE_DIR", "~/.cache/uv"),
    ("npm_config_cache", "~/.npm"),
    ("PIP_CACHE_DIR", "~/.cache/pip"),
    ("GOCACHE", "~/.cache/go-build"),
];

/// A fence made ready to be put up in the agent's child.
pub struct Walls {
    pub ruleset: Ruleset,
    pub proxy: Option<Proxy>,
    /// Whether the socket and listen filters go up too.
    pub sockets: bool,
    /// The fence as held here: granted the mirror, with its scratch.
    pub fence: Fence,
    /// The scratch the agent is given as its temporary directory.
    pub tmp: PathBuf,
    /// What the target is told of the fence with every command (`abroad.told`).
    pub told: Value,
    /// Whether the wall lets the agent change the mirror, and so the workspace: what the
    /// supervisor replays on the target is held to it (`Supervisor.writes`).
    pub writes: bool,
    /// The scratch this made, removed when the walls are dropped.
    _scratch: Option<Scratch>,
}

/// A scratch directory made for one session, removed with it.
struct Scratch(PathBuf);

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

impl Walls {
    /// Opens what `fence` lets be written and starts its proxy.
    ///
    /// # Errors
    /// `PermissionDenied` where this machine cannot put the wall up; `InvalidInput` where the
    /// fence was drawn path by path; what [`Fence::ready`] and [`Proxy::start`] fail with.
    pub fn ready(fence: &Fence) -> io::Result<Walls> {
        let able = crate::fence::able();
        let landlocked = if fence.online { able.fs } else { able.net };
        if !landlocked {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                format!(
                    "this machine cannot fence the agent: it needs Landlock{}",
                    if fence.online {
                        ""
                    } else {
                        " ABI 4 and seccomp"
                    }
                ),
            ));
        }
        let (tmp, scratch) = if fence.tmp.is_empty() {
            let made = scratch()?;
            (made.clone(), Some(Scratch(made)))
        } else {
            (PathBuf::from(&fence.tmp), None)
        };
        let held = Fence {
            tmp: tmp.to_string_lossy().into_owned(),
            ..fence.clone()
        };
        let told = told(&held)?;
        let proxy = if fence.online {
            None
        } else {
            Some(Proxy::start(&fence.hosts)?)
        };
        let port = proxy.as_ref().map(|proxy| proxy.port);
        // Made and opened here, before the agent is forked, and granted as the very
        // directories opened: never a link an earlier turn put at one of their names.
        let write = held.ready()?;
        let ruleset = Ruleset {
            read: held.read.iter().map(PathBuf::from).collect(),
            write,
            connect_ports: port.into_iter().collect(),
            // As `hmz internal fence` has them: a port the kernel picks, and the fence's own;
            // each held to loopback by the supervisor.
            bind_ports: match port {
                Some(_) => std::iter::once(0)
                    .chain(held.listen.iter().copied())
                    .collect(),
                None => Vec::new(),
            },
            net: port.is_some(),
        };
        Ok(Walls {
            ruleset,
            sockets: proxy.is_some(),
            proxy,
            writes: allows(&held, "/", true),
            fence: held,
            tmp,
            told,
            _scratch: scratch,
        })
    }

    /// [`Walls::ready`] around a supervised agent whose workspace is the mirror at `mirror`:
    /// granted as the fence's local level grants the workspace (`read` or `all`).
    pub fn around(fence: &Fence, mirror: &Path) -> io::Result<Walls> {
        let granted = granting(fence, &mirror.to_string_lossy());
        let mut walls = Walls::ready(&granted)?;
        walls.writes = allows(&walls.fence, &mirror.to_string_lossy(), true);
        Ok(walls)
    }

    /// The variables the agent is started with inside the walls (`TMPDIR`, proxy variables).
    pub fn environ(&self) -> Vec<(String, String)> {
        self.overrides(|name| std::env::var(name).ok())
    }

    /// `given`, with [`Walls::environ`] said over it as `wrap.environ` says it.
    pub fn environ_over(&self, given: Vec<(OsString, OsString)>) -> Vec<(OsString, OsString)> {
        let said = self.overrides(|name| {
            given
                .iter()
                .find(|(key, _)| key == name)
                .map(|(_, value)| value.to_string_lossy().into_owned())
        });
        let mut env = given;
        for (name, value) in said {
            overlay(&mut env, name.into(), value.into());
        }
        env
    }

    /// What `wrap.environ` sets over an environment `lookup` reads.
    fn overrides(&self, lookup: impl Fn(&str) -> Option<String>) -> Vec<(String, String)> {
        let tmp = self.tmp.to_string_lossy().into_owned();
        let mut said: Vec<(String, String)> = ["TMPDIR", "TMP", "TEMP"]
            .iter()
            .map(|name| ((*name).to_owned(), tmp.clone()))
            .collect();
        for (name, usual) in CACHES {
            let at = lookup(name)
                .filter(|at| !at.is_empty())
                .unwrap_or_else(|| expanduser(usual));
            if !(at.starts_with('/') && allows(&self.fence, &at, true)) {
                let instead = self.tmp.join("cache").join(name.to_lowercase());
                said.push((name.to_owned(), instead.to_string_lossy().into_owned()));
            }
        }
        if let Some(proxy) = &self.proxy {
            let at = format!("http://127.0.0.1:{}", proxy.port);
            said.extend(PROXIES.iter().map(|name| ((*name).to_owned(), at.clone())));
            // Emptied rather than removed: a `NO_PROXY` somebody exported would otherwise send
            // the hosts it names around the proxy, into a wall.
            said.extend([
                ("NO_PROXY".to_owned(), String::new()),
                ("no_proxy".to_owned(), String::new()),
                ("NODE_USE_ENV_PROXY".to_owned(), "1".to_owned()),
            ]);
        }
        said
    }
}

/// A path as a fence holds it (`fence._normal`): absolute, with no `..`.
fn absolute(path: &str) -> String {
    abspath(path).unwrap_or_else(|_| normpath(path))
}

/// Sets `name` in `env`, in its place where it is there already.
pub fn overlay(env: &mut Vec<(OsString, OsString)>, name: OsString, value: OsString) {
    match env.iter_mut().find(|(key, _)| *key == name) {
        Some(slot) => slot.1 = value,
        None => env.push((name, value)),
    }
}

/// `Fence.granting(read=[mirror] if level == READ, write=[mirror] if level == ALL)`, where
/// `level` is the first of the fence's scopes; a path granted to write is not also in `read`.
pub fn granting(fence: &Fence, mirror: &str) -> Fence {
    let level = fence.scopes.first().map(String::as_str).unwrap_or("");
    let mirror = absolute(mirror);
    let mut write: Vec<String> = Vec::new();
    for one in fence.write.iter().map(|one| absolute(one)) {
        if !write.contains(&one) {
            write.push(one);
        }
    }
    if level == "all" && !write.contains(&mirror) {
        write.push(mirror.clone());
    }
    let mut read: Vec<String> = Vec::new();
    let wanted = fence
        .read
        .iter()
        .map(|one| absolute(one))
        .chain((level == "read").then_some(mirror));
    for one in wanted {
        if !write.contains(&one) && !read.contains(&one) {
            read.push(one);
        }
    }
    Fence {
        read,
        write,
        ..fence.clone()
    }
}

/// `Fence.allows`: whether some root the fence grants holds `path`, taken as written.
pub fn allows(fence: &Fence, path: &str, write: bool) -> bool {
    let Ok(held) = abspath(path) else {
        return false;
    };
    let roots = fence
        .write
        .iter()
        .chain(fence.read.iter().filter(|_| !write));
    roots
        .map(|root| absolute(root))
        .any(|root| held == root || held.starts_with(&format!("{}/", root.trim_end_matches('/'))))
}

/// `abroad.told(fence, native=False)`: the levels and `online`, and the scratch, for the
/// target to keep its own at the same path -- the agent writes that path into the commands it
/// runs there.
pub fn told(fence: &Fence) -> io::Result<Value> {
    let [local, user, system] = fence.scopes.as_slice() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "a fence drawn path by path cannot be drawn again on another machine",
        ));
    };
    let mut said = json!({
        "local": local,
        "user": user,
        "system": system,
        "online": fence.online,
    });
    if !fence.tmp.is_empty() {
        said["tmp"] = Value::from(fence.tmp.clone());
    }
    Ok(said)
}

/// `~/...` under this process's `$HOME`.
fn expanduser(path: &str) -> String {
    match (path.strip_prefix("~/"), std::env::var("HOME")) {
        (Some(rest), Ok(home)) => format!("{}/{rest}", home.trim_end_matches('/')),
        _ => path.to_owned(),
    }
}

/// `tempfile.mkdtemp(prefix="hmz-fence-")`: a new directory only this user may enter.
fn scratch() -> io::Result<PathBuf> {
    let under = std::env::temp_dir();
    loop {
        let at = under.join(format!("hmz-fence-{:08x}", rand::random::<u32>()));
        match std::fs::DirBuilder::new().mode(0o700).create(&at) {
            Ok(()) => return Ok(at),
            Err(why) if why.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(why) => return Err(why),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn levelled(level: &str, online: bool) -> Fence {
        Fence {
            read: vec!["/usr".into(), "/m".into()],
            write: vec!["/w/".into()],
            online,
            scopes: vec![level.into(), "read".into(), "read".into()],
            ..Fence::default()
        }
    }

    #[test]
    fn the_mirror_is_granted_as_the_workspace_is() {
        let all = granting(&levelled("all", true), "/m");
        assert_eq!(all.write, ["/w", "/m"]);
        assert_eq!(all.read, ["/usr"]);
        assert!(allows(&all, "/m/x", true));

        let read = granting(&levelled("read", true), "/mirror");
        assert_eq!(read.read, ["/usr", "/m", "/mirror"]);
        assert!(!allows(&read, "/mirror", true));
        assert!(allows(&read, "/mirror/x", false));

        let none = granting(&levelled("none", true), "/mirror");
        assert!(!allows(&none, "/mirror", false));
    }

    #[test]
    fn a_root_holds_what_is_beneath_it_and_nothing_beside_it() {
        let fence = levelled("all", true);
        assert!(allows(&fence, "/w", true));
        assert!(allows(&fence, "/w/a/../b", true));
        assert!(!allows(&fence, "/wx", true));
        assert!(!allows(&fence, "/usr/bin", true));
        assert!(allows(&fence, "/usr/bin", false));
        let everything = Fence {
            write: vec!["/".into()],
            ..Fence::default()
        };
        assert!(allows(&everything, "/anything", true));
    }

    #[test]
    fn the_target_is_told_the_levels_and_the_scratch() {
        let fence = Fence {
            tmp: "/tmp/hmz-fence-x".into(),
            ..levelled("all", false)
        };
        assert_eq!(
            told(&fence).unwrap().to_string(),
            r#"{"local":"all","user":"read","system":"read","online":false,"tmp":"/tmp/hmz-fence-x"}"#
        );
        let path_by_path = Fence {
            scopes: Vec::new(),
            ..fence
        };
        assert_eq!(
            told(&path_by_path).unwrap_err().kind(),
            io::ErrorKind::InvalidInput
        );
    }

    #[test]
    fn the_agent_is_given_the_scratch_and_caches_it_may_write() {
        let walls = Walls {
            ruleset: Ruleset::default(),
            proxy: None,
            sockets: false,
            fence: Fence {
                write: vec!["/w".into()],
                online: true,
                ..Fence::default()
            },
            tmp: PathBuf::from("/s"),
            told: Value::Null,
            writes: true,
            _scratch: None,
        };
        let env = walls.environ_over(vec![
            ("PATH".into(), "/bin".into()),
            ("XDG_CACHE_HOME".into(), "/w/cache".into()),
            ("GOCACHE".into(), "relative".into()),
        ]);
        let said = |name: &str| {
            env.iter()
                .find(|(key, _)| key == name)
                .map(|(_, value)| value.to_string_lossy().into_owned())
        };
        assert_eq!(said("PATH").as_deref(), Some("/bin"));
        assert_eq!(said("TMPDIR").as_deref(), Some("/s"));
        assert_eq!(said("TEMP").as_deref(), Some("/s"));
        assert_eq!(said("XDG_CACHE_HOME").as_deref(), Some("/w/cache"));
        assert_eq!(said("GOCACHE").as_deref(), Some("/s/cache/gocache"));
        assert_eq!(
            said("npm_config_cache").as_deref(),
            Some("/s/cache/npm_config_cache")
        );
        assert_eq!(said("HTTPS_PROXY"), None);
        assert_eq!(env[0].0, "PATH");
    }

    #[test]
    fn a_variable_is_set_in_its_place() {
        let mut env = vec![("A".into(), "1".into()), ("B".into(), "2".into())];
        overlay(&mut env, "A".into(), "3".into());
        overlay(&mut env, "C".into(), "4".into());
        let said: Vec<(OsString, OsString)> = vec![
            ("A".into(), "3".into()),
            ("B".into(), "2".into()),
            ("C".into(), "4".into()),
        ];
        assert_eq!(env, said);
    }

    #[test]
    fn a_scratch_is_made_private_and_removed_with_it() {
        use std::os::unix::fs::PermissionsExt;
        let at = scratch().unwrap();
        let mode = std::fs::metadata(&at).unwrap().permissions().mode();
        assert_eq!(mode & 0o777, 0o700);
        drop(Scratch(at.clone()));
        assert!(!at.exists());
    }
}
