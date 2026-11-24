//! Shipping coganchor down a road, against a fake `ssh` that runs what it is handed here.
//!
//! The fake stands in for the far side as `tests/integration/doubles_anchor.py`'s does: it
//! skips ssh's options and the destination and runs the one command string with `/bin/sh`,
//! with `HOME` pointed at a directory of the test's own.

use std::ffi::OsString;
use std::fs;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, SystemTime};

use coganchor::transport::{Road, Target, ship};

/// The scratch world every test here shares: the fake `ssh` first on `PATH`, `$HOME` for the
/// far side, and a directory of builds. Set up once, as the environment is the process's.
struct World {
    root: PathBuf,
    home: PathBuf,
    calls: PathBuf,
    build: PathBuf,
}

fn world() -> &'static World {
    static WORLD: OnceLock<World> = OnceLock::new();
    WORLD.get_or_init(|| {
        let root = tempfile::tempdir().unwrap().keep();
        let bin = root.join("bin");
        let home = root.join("home");
        let platform = ship::here().unwrap();
        let builds = root.join("builds");
        let build = builds.join(&platform).join("coganchor");
        fs::create_dir_all(&bin).unwrap();
        fs::create_dir_all(&home).unwrap();
        fs::create_dir_all(build.parent().unwrap()).unwrap();
        let calls = root.join("calls");
        let ssh = bin.join("ssh");
        fs::write(
            &ssh,
            "#!/bin/sh\n\
             echo \"$*\" >> \"$FAKE_CALLS\"\n\
             while [ $# -gt 0 ]; do\n\
               case \"$1\" in\n\
                 -o|-p|-F) shift 2 ;;\n\
                 -*) shift ;;\n\
                 *) shift; break ;;\n\
               esac\n\
             done\n\
             export REAL_HOME=\"$HOME\"\n\
             unset XDG_CACHE_HOME\n\
             HOME=\"$FAKE_HOME\" exec /bin/sh -c \"$1\"\n",
        )
        .unwrap();
        fs::set_permissions(&ssh, fs::Permissions::from_mode(0o755)).unwrap();
        // A build that is the Python anchor in disguise: `coganchor anchor ARGS` is
        // `hmz internal anchor serve ARGS`, run from this checkout.
        let checkout = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        fs::write(
            &build,
            format!(
                "#!/bin/sh\n\
                 shift\n\
                 HOME=\"$REAL_HOME\" exec uv run --quiet --project '{}' \
                 python -m hmz internal anchor serve \"$@\"\n",
                checkout.canonicalize().unwrap().display()
            ),
        )
        .unwrap();
        fs::set_permissions(&build, fs::Permissions::from_mode(0o755)).unwrap();
        let path = std::env::var("PATH").unwrap_or_default();
        // SAFETY: set once, before any test here reads the environment or starts a process.
        unsafe {
            std::env::set_var("PATH", format!("{}:{path}", bin.display()));
            std::env::set_var("FAKE_HOME", &home);
            std::env::set_var("FAKE_CALLS", &calls);
            std::env::set_var("HUMANIZE_SSH_REUSE", "off");
            std::env::set_var(ship::BINARIES, &builds);
            std::env::remove_var("HUMANIZE_COGANCHOR");
        }
        World {
            root,
            home,
            calls,
            build,
        }
    })
}

/// How many times the fake `ssh` has been run to `me@far` (the other test goes elsewhere).
fn calls() -> usize {
    fs::read_to_string(&world().calls).map_or(0, |said| {
        said.lines()
            .filter(|line| line.contains(" me@far "))
            .count()
    })
}

fn mtime(path: &str) -> SystemTime {
    fs::metadata(path).unwrap().modified().unwrap()
}

fn age(path: &Path, days: u64) {
    let then = SystemTime::now() - Duration::from_secs(days * 24 * 3600);
    fs::File::options()
        .append(true)
        .open(path)
        .unwrap()
        .set_modified(then)
        .unwrap();
}

#[test]
fn installs_once_and_reuses_it() {
    let world = world();
    let road = Road::to(&Target::parse("ssh://me@far:2222?F=/dev/null").unwrap());
    let before = calls();

    let path = ship::installed(&road).unwrap();
    let digest = ship::digest(&world.build).unwrap();
    let cache = world.home.join(".cache/humanize");
    assert_eq!(
        path,
        cache.join(format!("coganchor-{digest}")).to_str().unwrap()
    );
    assert_eq!(fs::read(&path).unwrap(), fs::read(&world.build).unwrap());
    assert_eq!(fs::metadata(&path).unwrap().mode() & 0o777, 0o700);
    // One probe, one install.
    assert_eq!(calls() - before, 2);

    // Asked again by this process: nothing crosses.
    assert_eq!(ship::installed(&road).unwrap(), path);
    assert_eq!(calls() - before, 2);

    // Asked by a process that has not been there: found, touched and not rewritten; and a
    // binary nobody has touched for weeks swept.
    let inode = fs::metadata(&path).unwrap().ino();
    age(Path::new(&path), 3);
    let stale = cache.join("coganchor-0000000000000000");
    fs::write(&stale, b"old").unwrap();
    age(&stale, 20);
    let fresh = cache.join("coganchor-1111111111111111");
    fs::write(&fresh, b"recent").unwrap();
    ship::forget(&road);
    assert_eq!(ship::installed(&road).unwrap(), path);
    assert_eq!(calls() - before, 4);
    assert_eq!(fs::metadata(&path).unwrap().ino(), inode);
    assert!(mtime(&path) > SystemTime::now() - Duration::from_secs(3600));
    assert!(!stale.exists());
    assert!(fresh.exists());
    let left: Vec<String> = fs::read_dir(&cache)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().into_string().unwrap())
        .collect();
    assert_eq!(left.len(), 2, "{left:?}");

    // And the line that runs it there.
    let line = ship::command(
        &road,
        &[OsString::from("anchor"), OsString::from("--stdio")],
    )
    .unwrap();
    let last = line.last().unwrap().to_str().unwrap();
    assert_eq!(last, format!("exec {path} anchor --stdio"));
    assert_eq!(line[0], "ssh");
    assert_eq!(line[1..3], ["-F", "/dev/null"]);
    let _ = &world.root;
}
