//! Putting coganchor on a target. [Unit 7]
//!
//! The target is asked its `uname -sm` once; the binary built for that OS and architecture is
//! found beside this one (`$COGANCHOR_BINARIES/<os>-<arch>/coganchor`, which `hmz` sets to the
//! wheel's `bin/` directory) and piped down the road into `<cache>/coganchor-<digest16>`,
//! written aside and renamed, mode 0700, unless a file of that name is already there; files of
//! that pattern untouched for 14 days are swept.
//!
//! This replaces the zipapp `Road.installed` and `_installing` in `hmz.coganchor.transport`
//! shipped, keeping what made that cheap: a binary is named by its digest, so a machine that
//! already holds it is only touched, and this process asks each machine once.

use std::collections::HashMap;
use std::ffi::OsString;
use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use sha2::{Digest, Sha256};

use crate::transport::Road;

/// The variable naming the directory of builds, one `<os>-<arch>/coganchor` per platform.
pub const BINARIES: &str = "COGANCHOR_BINARIES";

/// How many hex digits of a binary's SHA-256 name it on a target. `transport._DIGEST`.
pub const DIGEST: usize = 16;

/// How many days a binary nothing has touched is kept on a target. `transport._KEPT_FOR`.
pub const KEPT_DAYS: u32 = 14;

/// Each target's `<os>-<arch>`, by its spelling, asked once per process.
static PROBED: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

/// Where each target holds each binary, by `(spelling, digest)`: a road walked twice is not
/// paid for twice. `transport._PUSHED`.
static PUSHED: Mutex<Option<HashMap<(String, String), String>>> = Mutex::new(None);

/// Each local build's digest, by path, size and modification time.
type Versions = HashMap<(PathBuf, u64, i64), String>;
static DIGESTS: Mutex<Option<Versions>> = Mutex::new(None);

/// Where coganchor is on the target behind `road`, shipping it there first if need be.
///
/// The path is the far side's own, `$HOME` already expanded there, so it can be run as one
/// word down any road. For a `local` target it is this very program.
pub fn installed(road: &Road) -> io::Result<String> {
    if road.target.scheme == "local" {
        return Ok(myself()?.to_string_lossy().into_owned());
    }
    let described = road.target.describe();
    let platform = platform(road)?;
    let binary = build(&platform)?;
    let digest = digest(&binary)?;
    let key = (described.clone(), digest.clone());
    if let Some(path) = PUSHED
        .lock()
        .unwrap()
        .get_or_insert_with(HashMap::new)
        .get(&key)
    {
        return Ok(path.clone());
    }
    let carried = fs::read(&binary)?;
    // What is sent is what is named, even for a build replaced since it was digested.
    let digest = hex::encode(Sha256::digest(&carried))[..DIGEST].to_owned();
    let key = (described.clone(), digest.clone());
    let script = installing(&road.cache(), &digest, carried.len() as u64, road.owned());
    let argv: Vec<OsString> = ["/bin/sh", "-c", &script, "coganchor"]
        .into_iter()
        .map(OsString::from)
        .collect();
    let result = road.run(&argv, &carried, None)?;
    let said = String::from_utf8_lossy(&result.stdout);
    // A cache named outright (a container's `/tmp/humanize`) is where the binary is, spelled
    // as every later command on that road will spell it; only one under `$HOME` needs the
    // target's own expansion of it, which is what the script prints last.
    let cache = road.cache();
    let path = if cache.starts_with('/') {
        format!("{}/coganchor-{digest}", cache.trim_end_matches('/'))
    } else {
        said.lines().last().unwrap_or("").trim().to_owned()
    };
    if !result.status.success() || !path.starts_with('/') {
        return Err(io::Error::other(format!(
            "could not install coganchor on {described}: {}",
            String::from_utf8_lossy(&result.stderr).trim()
        )));
    }
    PUSHED
        .lock()
        .unwrap()
        .get_or_insert_with(HashMap::new)
        .insert(key, path.clone());
    Ok(path)
}

/// The command line running `coganchor <args>` on the target behind `road`.
pub fn command(road: &Road, args: &[OsString]) -> io::Result<Vec<OsString>> {
    let mut argv = vec![OsString::from(installed(road)?)];
    argv.extend(args.iter().cloned());
    // A local road has no prefix: this is `[current_exe, ...args]` there.
    road.try_line(&argv)
}

/// Forgets what this process shipped to the machine behind `road`, for one that has been
/// replaced: a container made again under an old name holds nothing. Every spelling of that
/// machine is forgotten, whoever it named as using it. Port of `Road.forget`.
pub fn forget(road: &Road) {
    let named = machine(&road.target.describe());
    if let Some(pushed) = PUSHED.lock().unwrap().as_mut() {
        pushed.retain(|(spelled, _), _| machine(spelled) != named);
    }
    if let Some(probed) = PROBED.lock().unwrap().as_mut() {
        probed.retain(|spelled, _| machine(spelled) != named);
    }
}

/// The machine a spelling names: a docker target without the options that say who uses it.
fn machine(spelled: &str) -> String {
    match crate::transport::Target::parse(spelled) {
        Ok(mut target) if target.scheme == "docker" => {
            target.options.clear();
            target.describe()
        }
        _ => spelled.to_owned(),
    }
}

/// The target's `<os>-<arch>`, asked with `uname -sm` once per target per process.
pub fn platform(road: &Road) -> io::Result<String> {
    let described = road.target.describe();
    if let Some(known) = PROBED
        .lock()
        .unwrap()
        .get_or_insert_with(HashMap::new)
        .get(&described)
    {
        return Ok(known.clone());
    }
    // Through the shell, which finds `uname` on its PATH: a road such as `srun` may run the
    // program it is handed without looking it up.
    let probe = ["/bin/sh", "-c", "exec uname -sm"].map(OsString::from);
    let result = road.run(&probe, b"", None)?;
    let said = String::from_utf8_lossy(&result.stdout);
    let words: Vec<&str> = said.split_whitespace().collect();
    let found = match (result.status.success(), words.as_slice()) {
        (true, [system, machine]) => named(system, machine),
        _ => None,
    };
    let Some(found) = found else {
        return Err(io::Error::other(format!(
            "could not tell what {described} is: `uname -sm` said {:?}{}",
            said.trim(),
            match String::from_utf8_lossy(&result.stderr).trim() {
                "" => String::new(),
                error => format!(" ({error})"),
            }
        )));
    };
    PROBED
        .lock()
        .unwrap()
        .get_or_insert_with(HashMap::new)
        .insert(described, found.clone());
    Ok(found)
}

/// The directory under `bin/` holding the build for a machine, as `uname -sm` names it:
/// `linux` or `darwin`, then `x86_64` or `aarch64`. Port of `hmz.coganchor.binary.named`.
pub fn named(system: &str, machine: &str) -> Option<String> {
    let os = system.trim().to_lowercase();
    let arch = match machine.trim().to_lowercase().as_str() {
        "x86_64" | "amd64" => "x86_64",
        "aarch64" | "arm64" => "aarch64",
        _ => return None,
    };
    matches!(os.as_str(), "linux" | "darwin").then(|| format!("{os}-{arch}"))
}

/// This machine's `<os>-<arch>`.
pub fn here() -> Option<String> {
    let uts = nix::sys::utsname::uname().ok()?;
    named(
        &uts.sysname().to_string_lossy(),
        &uts.machine().to_string_lossy(),
    )
}

/// The local build of coganchor for `platform`: `$COGANCHOR_BINARIES/<platform>/coganchor`
/// where that is a file, else this very program where it was built for that platform.
pub fn build(platform: &str) -> io::Result<PathBuf> {
    let listed = std::env::var_os(BINARIES)
        .filter(|said| !said.is_empty())
        .map(|dir| Path::new(&dir).join(platform).join("coganchor"));
    if let Some(path) = &listed
        && path.is_file()
    {
        return Ok(path.clone());
    }
    if here().as_deref() == Some(platform) {
        return myself();
    }
    Err(io::Error::new(
        io::ErrorKind::NotFound,
        match listed {
            Some(path) => format!(
                "no coganchor built for {platform}: {} is not a file",
                path.display()
            ),
            None => format!("no coganchor built for {platform}: {BINARIES} is not set"),
        },
    ))
}

/// This program.
///
/// On Linux a program replaced on disk while it runs is named `PATH (deleted)`, which is no
/// file; `/proc/self/exe` still opens and runs what is running, so that is used instead.
fn myself() -> io::Result<PathBuf> {
    let path = std::env::current_exe()?;
    let running = Path::new("/proc/self/exe");
    if !path.exists() && running.exists() {
        return Ok(running.to_owned());
    }
    Ok(path)
}

/// The first [`DIGEST`] hex digits of a file's SHA-256, worked out once per version of it.
pub fn digest(path: &Path) -> io::Result<String> {
    let found = fs::metadata(path)?;
    let key = (
        path.to_owned(),
        found.size(),
        found.mtime_nsec() + found.mtime() * 1_000_000_000,
    );
    if let Some(known) = DIGESTS
        .lock()
        .unwrap()
        .get_or_insert_with(HashMap::new)
        .get(&key)
    {
        return Ok(known.clone());
    }
    let digest = hex::encode(Sha256::digest(fs::read(path)?))[..DIGEST].to_owned();
    DIGESTS
        .lock()
        .unwrap()
        .get_or_insert_with(HashMap::new)
        .insert(key, digest.clone());
    Ok(digest)
}

/// The `sh` script that installs the binary arriving on its input, run on the far side, which
/// prints where it is. Port of `_installing` and `python_command`'s `owned` checks.
///
/// `cache` is spelled as that machine's shell reads it, `$HOME` and all. Where `owned`, the
/// cache has to be a directory of the far side's user's alone before anything goes in it
/// (protocol/core.md 6.9.1.8).
///
/// A name is only a promise, as `_INSTALL_SOURCE` has it: what arrived and what is already
/// there are both checked against `size` and `digest` before they are believed (the digest
/// with `sha256sum` or `shasum` where that machine has one), so a stream cut short or a file
/// somebody else left under the name is never what runs. A binary already there that checks
/// out is only touched, so the sweep counts it as used, and its input left unread -- with
/// `touch -c -h`, which sets the time by name, where a plain `touch`, and uutils' with `-c`
/// alone, opens the file for writing and Linux refuses to run a file anybody has open so
/// (`Text file busy`); otherwise
/// it is written under a name of its own, `<file>.humanize-<pid>-1.tmp` (protocol/files.md
/// 9.3.4: a fleet coming up installs on one machine by the hundred), and moved into place, so
/// whoever runs it finds the whole binary or none. Then every `coganchor-*` nothing has
/// touched in [`KEPT_DAYS`] days goes.
pub fn installing(cache: &str, digest: &str, size: u64, owned: bool) -> String {
    let mut script = String::from("umask 077; ");
    script += &format!("d=\"{cache}\"; ");
    if owned {
        script += "mkdir -p \"$d\" && [ -d \"$d\" ] && [ ! -L \"$d\" ] && [ -O \"$d\" ] && \
                   chmod 700 \"$d\" || \
                   { echo \"coganchor: $d is not a directory this user owns\" >&2; exit 1; }; ";
    } else {
        script += "mkdir -p \"$d\" || exit 1; ";
    }
    script += &format!("f=\"$d/coganchor-{digest}\"; ");
    script += &format!(
        "summed() {{ \
           if command -v sha256sum >/dev/null 2>&1; then s=$(sha256sum < \"$1\"); \
           elif command -v shasum >/dev/null 2>&1; then s=$(shasum -a 256 < \"$1\"); \
           else return 0; fi; \
           case \"$s\" in {digest}*) return 0 ;; esac; return 1; }}; \
         whole() {{ [ -f \"$1\" ] && [ ! -L \"$1\" ] && [ -O \"$1\" ] && \
           [ \"$(wc -c < \"$1\" | tr -d ' ')\" = {size} ] && summed \"$1\"; }}; "
    );
    script += &format!(
        "if whole \"$f\" && [ -x \"$f\" ] && touch -c -h \"$f\"; then :; else \
           t=\"$f.humanize-$$-1.tmp\"; \
           cat > \"$t\" && whole \"$t\" && chmod 700 \"$t\" && mv -f \"$t\" \"$f\" || \
           {{ rm -f \"$t\"; \
              echo \"coganchor: what arrived at $f is not coganchor-{digest}\" >&2; exit 1; }}; \
         fi; "
    );
    script += &format!(
        "find \"$d\" -maxdepth 1 -type f -name 'coganchor-*' -mtime +{KEPT_DAYS} \
         -exec rm -f {{}} \\; 2>/dev/null; "
    );
    script += "printf '%s\\n' \"$f\"";
    script
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::os::unix::fs::PermissionsExt;
    use std::process::{Command, Output, Stdio};

    #[test]
    fn platforms_are_named_as_binary_named_names_them() {
        assert_eq!(named("Linux", "x86_64").as_deref(), Some("linux-x86_64"));
        assert_eq!(named("Darwin", "arm64").as_deref(), Some("darwin-aarch64"));
        assert_eq!(named(" linux ", "AMD64").as_deref(), Some("linux-x86_64"));
        assert_eq!(named("Linux", "aarch64").as_deref(), Some("linux-aarch64"));
        assert_eq!(named("FreeBSD", "amd64"), None);
        assert_eq!(named("Linux", "riscv64"), None);
        assert!(here().is_some());
    }

    #[test]
    fn this_machine_is_its_own_build() {
        assert_eq!(build(&here().unwrap()).unwrap(), myself().unwrap());
    }

    /// Runs the installer here, against `cache`, for a binary that is `meant`, fed `input`.
    fn install(cache: &Path, meant: &[u8], input: &[u8], owned: bool) -> Output {
        let digest = &hex::encode(Sha256::digest(meant))[..DIGEST];
        let script = installing(cache.to_str().unwrap(), digest, meant.len() as u64, owned);
        let mut child = Command::new("/bin/sh")
            .args(["-c", &script, "coganchor"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let _ = child.stdin.take().unwrap().write_all(input);
        child.wait_with_output().unwrap()
    }

    #[test]
    fn installs_once_and_then_touches() {
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path().join("c");
        let output = install(&cache, b"first", b"first", true);
        assert!(output.status.success());
        let path = String::from_utf8(output.stdout).unwrap().trim().to_owned();
        let digest = &hex::encode(Sha256::digest(b"first"))[..DIGEST];
        assert_eq!(
            path,
            cache.join(format!("coganchor-{digest}")).to_str().unwrap()
        );
        assert_eq!(fs::read(&path).unwrap(), b"first");
        assert_eq!(fs::metadata(&path).unwrap().mode() & 0o777, 0o700);
        assert_eq!(fs::metadata(&cache).unwrap().mode() & 0o777, 0o700);
        // There already: kept as it is, its input unread.
        let output = install(&cache, b"first", b"", false);
        assert!(output.status.success());
        assert_eq!(String::from_utf8(output.stdout).unwrap().trim(), path);
        assert_eq!(fs::read(&path).unwrap(), b"first");
        assert_eq!(fs::read_dir(&cache).unwrap().count(), 1);
    }

    #[test]
    fn what_does_not_check_out_is_not_believed() {
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path().join("c");
        // Cut short on the way: refused, and nothing left behind.
        let output = install(&cache, b"the whole binary", b"the whole", false);
        assert!(!output.status.success());
        assert!(String::from_utf8_lossy(&output.stderr).contains("is not coganchor-"));
        assert_eq!(fs::read_dir(&cache).unwrap().count(), 0);
        // Something else under its name: replaced.
        let digest = &hex::encode(Sha256::digest(b"the whole binary"))[..DIGEST];
        let named = cache.join(format!("coganchor-{digest}"));
        fs::write(&named, b"an impostor here").unwrap();
        fs::set_permissions(&named, fs::Permissions::from_mode(0o700)).unwrap();
        let output = install(&cache, b"the whole binary", b"the whole binary", false);
        assert!(output.status.success());
        assert_eq!(fs::read(&named).unwrap(), b"the whole binary");
    }

    #[test]
    fn a_cache_somebody_linked_is_refused() {
        let dir = tempfile::tempdir().unwrap();
        let real = dir.path().join("real");
        fs::create_dir(&real).unwrap();
        let link = dir.path().join("link");
        std::os::unix::fs::symlink(&real, &link).unwrap();
        let output = install(&link, b"x", b"x", true);
        assert!(!output.status.success());
        assert!(String::from_utf8_lossy(&output.stderr).contains("is not a directory"));
        assert_eq!(fs::read_dir(&real).unwrap().count(), 0);
    }
}
