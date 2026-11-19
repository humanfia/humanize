//! Bubblewrap: a fence put up with namespaces, where Landlock cannot hold it.
//!
//! A Linux kernel older than 5.13, or booted without Landlock, holds no fence with Landlock at
//! all, and one older than 6.7 cannot cut the network with it. Most such kernels still lend an
//! unprivileged process a user namespace, and with it a mount namespace and a network
//! namespace of its own -- which is what `bwrap` builds a sandbox out of. So where `--sandbox`
//! leaves the choice to this machine and Landlock cannot, or where it names `bwrap`, a fence is
//! put up this way instead ([`crate::fence::backend`]).
//!
//! The program is given a root of its own, empty and read-only, and every path the fence
//! grants is mounted into it from this machine at the path it leads to -- read-only where it
//! may be read, writable where it may be written, the devices as devices -- the shallower
//! first, so that a deeper one is mounted over it. A carve-out is a mount too, over the grant
//! it lies beneath and before any grant at its own depth: read-only where it may be read, and
//! an empty read-only directory or an empty file where it may not be reached. What it writes
//! is mounted from the descriptor [`Fence::reached`] held it by, never from its name again, so
//! that what is mounted is what was checked. A link on the way to a granted path is made again
//! in the root, where no directory mounted from this machine already holds it.
//!
//! Where the network is cut the program gets a network namespace of its own, whose loopback is
//! the only interface it has; what still has to cross that edge -- the proxy that is the one
//! way out, and a port a CLI serves itself to its driver at -- is carried across it by
//! [`crate::fence::relay`], which the program is started beneath.
//!
//! It differs from Landlock in what a kernel lets it do. A carve-out that is not there cannot
//! be mounted over without making it on this machine, so a fence carving out such a path is
//! refused ([`carves`]) rather than held; and what is not granted is not there at all, rather
//! than there and unreachable.

use std::ffi::OsString;
use std::io;
use std::os::fd::RawFd;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use crate::fence::Fence;

/// Where `bwrap` is looked for where it is not on the `PATH`.
pub const PLACES: [&str; 3] = ["/usr/bin/bwrap", "/usr/local/bin/bwrap", "/bin/bwrap"];

/// The `bwrap` on this machine: on the `PATH`, else in [`PLACES`].
pub fn program() -> Option<PathBuf> {
    let on_path = std::env::var_os("PATH")
        .into_iter()
        .flat_map(|path| std::env::split_paths(&path).collect::<Vec<_>>())
        .map(|dir| dir.join("bwrap"));
    on_path
        .chain(PLACES.iter().map(PathBuf::from))
        .find(|one| runnable(one))
}

fn runnable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    path.metadata()
        .is_ok_and(|held| held.is_file() && held.permissions().mode() & 0o111 != 0)
}

/// Whether bubblewrap starts here, cutting the network too where `net`; asked of it once.
///
/// By starting it: a `bwrap` that is installed is not one that starts, on a kernel that lends
/// no unprivileged user namespace, in a container whose seccomp profile refuses one, or inside
/// a fence already -- Landlock forbids the mounts it is made of.
pub fn available(net: bool) -> bool {
    static FS: OnceLock<bool> = OnceLock::new();
    static NET: OnceLock<bool> = OnceLock::new();
    *(if net { &NET } else { &FS }).get_or_init(|| cfg!(target_os = "linux") && probe(net))
}

fn probe(net: bool) -> bool {
    let Some(bwrap) = program() else {
        return false;
    };
    let mut line = std::process::Command::new(&bwrap);
    line.args(["--ro-bind", "/", "/", "--die-with-parent"]);
    if net {
        line.arg("--unshare-net");
    }
    line.arg("--")
        .arg(&bwrap)
        .arg("--version")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

/// Refuses a fence whose carve-outs cannot be mounted over: one not there, which made later
/// inside a grant that writes it would be written.
pub fn carves(fence: &Fence) -> io::Result<()> {
    for path in fence.keep.iter().chain(&fence.deny) {
        if std::fs::symlink_metadata(path).is_err() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("{path}: bubblewrap cannot carve out a path that is not there"),
            ));
        }
    }
    Ok(())
}

fn depth(path: &str) -> usize {
    path.split('/').filter(|one| !one.is_empty()).count()
}

fn device(path: &str) -> bool {
    path == "/dev" || path.starts_with("/dev/")
}

/// Whether `path` is strictly beneath `root`.
fn beneath(path: &str, root: &str) -> bool {
    path != root && (root == "/" || path.starts_with(&format!("{root}/")))
}

/// Where a path leads, every link followed; `None` where it leads nowhere.
fn real(path: &str) -> Option<String> {
    std::fs::canonicalize(path)
        .ok()
        .map(|one| one.to_string_lossy().into_owned())
}

/// Every name on the way to a path, the path included, that is a symbolic link, each where it
/// is: beneath the directory the names before it lead to, links followed. `/bin/sh` is at
/// `/usr/bin/sh` where `/bin` is a link to `usr/bin`, and a `/usr` mounted from this machine
/// holds it already.
fn links(path: &str) -> Vec<String> {
    let mut at = String::new();
    let mut found = Vec::new();
    for part in path.split('/').filter(|one| !one.is_empty()) {
        at = format!("{at}/{part}");
        if Path::new(&at).is_symlink() {
            found.push(at.clone());
            match real(&at) {
                Some(led) => at = if led == "/" { String::new() } else { led },
                None => break,
            }
        }
    }
    found
}

/// The `bwrap` command line that puts a program inside a fence.
///
/// `reached` is what the fence writes, as [`Fence::reached`] held it, each path with the
/// descriptor holding it; one with none is not there, and is granted nothing. `bwrap` says the
/// program's pid on `info`, and the descriptors in `reached` and `info` have to be handed to
/// it open. `inner` is the program and its arguments -- the relay before it, where the network
/// is cut.
///
/// Every mount is made at the path it leads to, links followed: `bwrap` makes its mounts
/// before the root it builds is the program's, so a link at a mount's destination -- one
/// `/etc/localtime` is -- would be followed into a root that has nothing in it.
pub fn command(
    fence: &Fence,
    reached: &[(String, Option<RawFd>)],
    info: RawFd,
    inner: &[OsString],
    bwrap: &Path,
) -> Vec<OsString> {
    // Each mount as the depth it is at, whether it is a grant -- which at one depth is mounted
    // after a carve-out, being the wider -- and what says it.
    let mut mounts: Vec<(usize, u8, Vec<String>)> = Vec::new();
    let mut late: Vec<String> = Vec::new();
    for path in &fence.read {
        if let Some(at) = real(path) {
            let flag = if device(&at) {
                "--dev-bind"
            } else {
                "--ro-bind"
            };
            mounts.push((depth(&at), 1, vec![flag.into(), at.clone(), at]));
        }
    }
    for (at, fd) in reached {
        if let Some(fd) = fd {
            // A written root holds `/dev`, and `--bind` would leave no device in it to open.
            let flag = if at == "/" || device(at) {
                "--dev-bind"
            } else {
                "--bind"
            };
            mounts.push((
                depth(at),
                1,
                vec![flag.into(), format!("/proc/self/fd/{fd}"), at.clone()],
            ));
        }
    }
    for path in &fence.keep {
        if let Some(at) = real(path) {
            mounts.push((depth(&at), 0, vec!["--ro-bind".into(), at.clone(), at]));
        }
    }
    for path in &fence.deny {
        if let Some(at) = real(path) {
            if Path::new(&at).is_dir() {
                mounts.push((depth(&at), 0, vec!["--tmpfs".into(), at.clone()]));
                late.extend(["--remount-ro".into(), at]);
            } else {
                mounts.push((
                    depth(&at),
                    0,
                    vec!["--ro-bind".into(), "/dev/null".into(), at],
                ));
            }
        }
    }
    // What is mounted from this machine, and so holds every link beneath it as it is here.
    let held: Vec<String> = mounts
        .iter()
        .filter(|(_, _, said)| said[0] != "--tmpfs")
        .filter_map(|(_, _, said)| said.last().cloned())
        .collect();
    let named = fence
        .read
        .iter()
        .chain(&fence.write)
        .chain((!fence.tmp.is_empty()).then_some(&fence.tmp));
    let mut made: Vec<String> = Vec::new();
    for link in named.flat_map(|name| links(name)) {
        if made.contains(&link) || held.iter().any(|one| beneath(&link, one)) {
            continue;
        }
        if let Ok(to) = std::fs::read_link(&link) {
            mounts.push((
                depth(&link),
                1,
                vec![
                    "--symlink".into(),
                    to.to_string_lossy().into_owned(),
                    link.clone(),
                ],
            ));
            made.push(link);
        }
    }
    if !held.iter().any(|one| one == "/") {
        // The root bubblewrap makes is an empty one of its own: nothing is there but what is
        // mounted, and read-only once it all is, so nothing can be made there either.
        late.extend(["--remount-ro".into(), "/".into()]);
    }
    let mut said: Vec<OsString> = vec![
        bwrap.into(),
        "--die-with-parent".into(),
        "--info-fd".into(),
        info.to_string().into(),
    ];
    if !fence.online {
        said.push("--unshare-net".into());
    }
    mounts.sort_by_key(|(depth, grant, _)| (*depth, *grant));
    said.extend(
        mounts
            .into_iter()
            .flat_map(|(_, _, one)| one)
            .map(OsString::from),
    );
    said.extend(late.into_iter().map(OsString::from));
    said.push("--".into());
    said.extend(inner.iter().cloned());
    said
}

/// The program's pid, as `bwrap` says it on its info descriptor: read up to the end of the one
/// object rather than to the end of the stream, which the program may hold open as long as it
/// runs. `None` where `bwrap` said nothing, having failed before it started the program.
pub fn child(info: std::os::fd::OwnedFd) -> Option<i32> {
    use std::io::Read;
    let mut file = std::fs::File::from(info);
    let mut held = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let read = match file.read(&mut chunk) {
            Ok(0) | Err(_) => return None,
            Ok(read) => read,
        };
        held.extend_from_slice(&chunk[..read]);
        let mut stream =
            serde_json::Deserializer::from_slice(&held).into_iter::<serde_json::Value>();
        if let Some(Ok(said)) = stream.next() {
            return said
                .get("child-pid")
                .and_then(serde_json::Value::as_i64)
                .and_then(|pid| i32::try_from(pid).ok());
        }
    }
}

/// Linux: `run` from the scratch on, under bubblewrap; `walled` is the fence with its scratch.
#[cfg(target_os = "linux")]
pub(crate) fn put_up(fence: &Fence, walled: &Fence, argv: &[OsString]) -> Result<i32, String> {
    use std::os::fd::AsRawFd;

    use crate::exit;
    use crate::fence::policy::spelled;
    use crate::fence::relay;
    use crate::fence::wrap::{Scratch, Serving, environ, waited_aimed};

    let bwrap = program().ok_or("this machine cannot fence a program: it has no bwrap")?;
    carves(fence).map_err(|why| spelled(&why))?;
    let proxy = Serving::start(fence)?;
    let port = proxy.port();
    let through = if port.is_some() {
        Some(Scratch::fresh("hmz-relay-")?)
    } else {
        None
    };
    let mut inner: Vec<OsString> = argv.to_vec();
    let mut walled = walled.clone();
    let mut bridges = Vec::new();
    if let (Some(port), Some(through)) = (port, &through) {
        let ours = std::env::current_exe().map_err(|why| spelled(&why))?;
        let ours = ours.to_string_lossy().into_owned();
        // The relay is this program again, which the fence has to let run inside it.
        walled = walled.granting(
            std::slice::from_ref(&ours),
            std::slice::from_ref(&through.path),
            &[],
            &[],
        );
        bridges =
            relay::outside(&through.path, port, &fence.listen).map_err(|why| spelled(&why))?;
        inner = ["internal", "fence", "--relay", &through.path, "--"]
            .into_iter()
            .map(OsString::from)
            .collect();
        inner.insert(0, ours.into());
        inner.extend(argv.iter().cloned());
    }
    let reached = walled.reached(None).map_err(|why| spelled(&why))?;
    let (info, said) =
        nix::unistd::pipe2(nix::fcntl::OFlag::O_CLOEXEC).map_err(|errno| spelled(&errno.into()))?;
    let handed: Vec<RawFd> = std::iter::once(said.as_raw_fd())
        .chain(
            reached
                .iter()
                .filter_map(|(_, fd)| fd.as_ref().map(AsRawFd::as_raw_fd)),
        )
        .collect();
    for fd in &handed {
        // SAFETY: clearing close-on-exec on a descriptor this process holds open.
        unsafe { libc::fcntl(*fd, libc::F_SETFD, 0) };
    }
    let raw: Vec<(String, Option<RawFd>)> = reached
        .iter()
        .map(|(at, fd)| (at.clone(), fd.as_ref().map(AsRawFd::as_raw_fd)))
        .collect();
    let line = command(&walled, &raw, said.as_raw_fd(), &inner, &bwrap);
    let env = environ(fence, std::env::vars_os(), &walled.tmp, port);
    let spawned = std::process::Command::new(&line[0])
        .args(&line[1..])
        .env_clear()
        .envs(env)
        .spawn();
    drop(said);
    drop(reached);
    let child = match spawned {
        Ok(child) => child,
        Err(why) => return Err(spelled(&why)),
    };
    let pid = child.id() as libc::pid_t;
    let aimed = self::child(info);
    let status = waited_aimed(pid, aimed.unwrap_or(pid));
    for bridge in bridges {
        bridge.stop();
    }
    drop(proxy);
    drop(through);
    // A `bwrap` that never said it started the program put no fence up: it said why.
    Ok(if aimed.is_some() {
        status
    } else {
        exit::UNFENCED
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The mounts a command line says, in order, each as its flag and what it names.
    fn mounts(said: &[OsString]) -> Vec<Vec<String>> {
        let said: Vec<String> = said
            .iter()
            .map(|one| one.to_string_lossy().into_owned())
            .collect();
        let end = said.iter().position(|one| one == "--").unwrap();
        let mut held = Vec::new();
        let mut at = 0;
        while at < end {
            let width = match said[at].as_str() {
                "--ro-bind" | "--bind" | "--dev-bind" | "--symlink" => 3,
                "--tmpfs" | "--remount-ro" => 2,
                _ => {
                    at += 1;
                    continue;
                }
            };
            held.push(said[at..at + width].to_vec());
            at += width;
        }
        held
    }

    fn strings(said: &[&str]) -> Vec<String> {
        said.iter().map(|one| (*one).to_owned()).collect()
    }

    fn tmp() -> (tempfile::TempDir, String) {
        let dir = tempfile::tempdir().unwrap();
        let path = std::fs::canonicalize(dir.path())
            .unwrap()
            .to_string_lossy()
            .into_owned();
        (dir, path)
    }

    #[test]
    fn the_shallower_is_mounted_first_and_a_carve_out_before_a_grant() {
        let (_dir, root) = tmp();
        let work = format!("{root}/work");
        std::fs::create_dir_all(format!("{work}/secret")).unwrap();
        std::fs::create_dir_all(format!("{work}/kept")).unwrap();
        let fence = Fence {
            read: vec!["/usr".into()],
            write: vec![work.clone()],
            keep: vec![format!("{work}/kept")],
            deny: vec![format!("{work}/secret")],
            ..Fence::default()
        };

        let said = command(
            &fence,
            &[(work.clone(), Some(7))],
            9,
            &["cli".into(), "-x".into()],
            Path::new("bwrap"),
        );

        assert_eq!(
            &said[..4],
            &["bwrap", "--die-with-parent", "--info-fd", "9"]
        );
        assert!(!said.iter().any(|one| one == "--unshare-net"));
        assert_eq!(&said[said.len() - 2..], &["cli", "-x"]);
        let held = mounts(&said);
        let index = |one: &[&str]| held.iter().position(|it| *it == strings(one)).unwrap();
        assert!(
            index(&["--ro-bind", "/usr", "/usr"]) < index(&["--bind", "/proc/self/fd/7", &work])
        );
        assert!(
            index(&["--bind", "/proc/self/fd/7", &work])
                < index(&["--tmpfs", &format!("{work}/secret")])
        );
        index(&[
            "--ro-bind",
            &format!("{work}/kept"),
            &format!("{work}/kept"),
        ]);
        assert_eq!(
            &held[held.len() - 2..],
            &[
                strings(&["--remount-ro", &format!("{work}/secret")]),
                strings(&["--remount-ro", "/"]),
            ]
        );
    }

    #[test]
    fn a_carve_out_at_the_depth_of_a_grant_is_mounted_before_it() {
        let (_dir, root) = tmp();
        std::fs::create_dir(format!("{root}/a")).unwrap();
        let fence = Fence {
            write: vec![format!("{root}/b")],
            deny: vec![format!("{root}/a")],
            ..Fence::default()
        };

        let held = mounts(&command(
            &fence,
            &[(format!("{root}/b"), Some(3))],
            4,
            &["x".into()],
            Path::new("bwrap"),
        ));

        assert_eq!(held[0], strings(&["--tmpfs", &format!("{root}/a")]));
    }

    #[test]
    fn a_denied_file_is_an_empty_one() {
        let (_dir, root) = tmp();
        let secret = format!("{root}/secret.env");
        std::fs::write(&secret, "TOKEN=1").unwrap();
        let fence = Fence {
            write: vec![root.clone()],
            deny: vec![secret.clone()],
            ..Fence::default()
        };

        let held = mounts(&command(
            &fence,
            &[(root, Some(3))],
            4,
            &["x".into()],
            Path::new("bwrap"),
        ));

        assert!(held.contains(&strings(&["--ro-bind", "/dev/null", &secret])));
    }

    #[test]
    fn a_path_written_through_a_link_is_mounted_where_it_leads_and_linked_again() {
        let (_dir, root) = tmp();
        std::fs::create_dir_all(format!("{root}/data/codex")).unwrap();
        std::fs::create_dir(format!("{root}/home")).unwrap();
        let (name, at) = (format!("{root}/home/.codex"), format!("{root}/data/codex"));
        std::os::unix::fs::symlink(&at, &name).unwrap();
        let fence = Fence {
            write: vec![name.clone()],
            ..Fence::default()
        };

        let held = mounts(&command(
            &fence,
            &[(at.clone(), Some(5))],
            6,
            &["x".into()],
            Path::new("bwrap"),
        ));

        assert!(held.contains(&strings(&["--bind", "/proc/self/fd/5", &at])));
        assert!(held.contains(&strings(&["--symlink", &at, &name])));
    }

    #[test]
    fn a_link_in_a_mounted_directory_is_not_made_again() {
        let (_dir, root) = tmp();
        std::fs::create_dir(format!("{root}/real")).unwrap();
        std::os::unix::fs::symlink(format!("{root}/real"), format!("{root}/link")).unwrap();
        let fence = Fence {
            read: vec![root.clone(), format!("{root}/link")],
            ..Fence::default()
        };

        let held = mounts(&command(&fence, &[], 6, &["x".into()], Path::new("bwrap")));

        assert!(held.contains(&strings(&[
            "--ro-bind",
            &format!("{root}/real"),
            &format!("{root}/real")
        ])));
        assert!(!held.iter().any(|one| one[0] == "--symlink"));
    }

    #[test]
    fn a_link_reached_through_a_linked_directory_that_is_mounted_is_not_made_again() {
        // `/bin/sh` on a machine whose `/bin` is a link to `usr/bin`: with `/usr` mounted,
        // the link `sh` is in it already, and making it again is refused as existing.
        let (_dir, root) = tmp();
        std::fs::create_dir(format!("{root}/real")).unwrap();
        std::fs::write(format!("{root}/real/target"), "").unwrap();
        std::os::unix::fs::symlink("target", format!("{root}/real/inner")).unwrap();
        std::os::unix::fs::symlink("real", format!("{root}/link")).unwrap();
        let fence = Fence {
            read: vec![format!("{root}/real"), format!("{root}/link/inner")],
            ..Fence::default()
        };

        let held = mounts(&command(&fence, &[], 6, &["x".into()], Path::new("bwrap")));

        let made: Vec<_> = held.iter().filter(|one| one[0] == "--symlink").collect();
        assert_eq!(
            made,
            [&strings(&["--symlink", "real", &format!("{root}/link")])]
        );
    }

    #[test]
    fn a_path_not_there_is_granted_nothing() {
        let fence = Fence {
            read: vec!["/nowhere/at/all".into()],
            write: vec!["/nowhere".into()],
            ..Fence::default()
        };

        let said = command(
            &fence,
            &[("/nowhere".into(), None)],
            6,
            &["x".into()],
            Path::new("bwrap"),
        );

        assert!(
            !said
                .iter()
                .any(|one| one.to_string_lossy().starts_with("/nowhere"))
        );
    }

    #[test]
    fn devices_are_mounted_as_devices() {
        let fence = Fence {
            read: vec!["/dev/zero".into()],
            write: vec!["/dev/null".into()],
            ..Fence::default()
        };

        let held = mounts(&command(
            &fence,
            &[("/dev/null".into(), Some(5))],
            6,
            &["x".into()],
            Path::new("bwrap"),
        ));

        assert!(held.contains(&strings(&["--dev-bind", "/dev/zero", "/dev/zero"])));
        assert!(held.contains(&strings(&["--dev-bind", "/proc/self/fd/5", "/dev/null"])));
    }

    #[test]
    fn a_written_root_is_this_machines_with_its_devices_and_stays_writable() {
        let fence = Fence {
            write: vec!["/".into()],
            ..Fence::default()
        };

        let held = mounts(&command(
            &fence,
            &[("/".into(), Some(5))],
            6,
            &["x".into()],
            Path::new("bwrap"),
        ));

        assert_eq!(held, vec![strings(&["--dev-bind", "/proc/self/fd/5", "/"])]);
    }

    #[test]
    fn a_fence_that_cuts_the_network_gets_a_namespace_of_its_own() {
        let fence = Fence {
            online: false,
            ..Fence::default()
        };

        let said = command(&fence, &[], 6, &["x".into()], Path::new("bwrap"));

        assert!(said.iter().any(|one| one == "--unshare-net"));
    }

    #[test]
    fn carves_refuses_a_carve_out_that_is_not_there() {
        let (_dir, root) = tmp();
        let missing = Fence {
            write: vec![root.clone()],
            deny: vec![format!("{root}/missing")],
            ..Fence::default()
        };
        std::fs::create_dir(format!("{root}/kept")).unwrap();
        let there = Fence {
            write: vec![root.clone()],
            keep: vec![format!("{root}/kept")],
            ..Fence::default()
        };

        assert!(
            carves(&missing)
                .unwrap_err()
                .to_string()
                .contains("not there")
        );
        assert!(carves(&there).is_ok());
    }

    #[test]
    fn child_is_the_pid_bwrap_says_and_reads_no_further() {
        let (read, write) = nix::unistd::pipe().unwrap();
        nix::unistd::write(&write, b"{\n    \"child-pid\": 7\n}\n").unwrap();
        // The other end still open, as it is while the program that holds it runs.
        assert_eq!(child(read), Some(7));
        drop(write);
    }

    #[test]
    fn child_is_none_where_bwrap_said_nothing() {
        let (read, write) = nix::unistd::pipe().unwrap();
        drop(write);
        assert_eq!(child(read), None);
    }
}
