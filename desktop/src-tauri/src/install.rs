//! The `hmz` the app runs: the release's own, put and kept there by `uv tool` -- the user's uv,
//! or one the app downloads for itself -- just as a terminal user installs it. Never while an
//! `hmz` of another version holds running epics: an install takes its files from under them.

use std::ffi::OsStr;
#[cfg(unix)]
use std::fs;
#[cfg(windows)]
use std::io::Write;
use std::io::{BufRead, BufReader, Read};
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;

use flate2::read::GzDecoder;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::child;
use crate::server;
use crate::shell_env::{self, Env};

/// The uv the app downloads where the user has none, for each architecture, and its archive's
/// sha256 as astral-sh/uv published it: a Mac's, and on Windows WSL's Linux.
const UV: &str = "0.12.24";
#[cfg(unix)]
const UV_TARGET: &str = "apple-darwin";
#[cfg(unix)]
const UV_SHA256: [(&str, &str); 2] = [
    (
        "aarch64",
        "0c4346de7abdb49495b393b9ec809fe387aa43e586be20fecb972216c1e71732",
    ),
    (
        "x86_64",
        "4fa82e37cb94767661f532b001e470b67a186c7260e305bd84ddb78fd545c0b6",
    ),
];
#[cfg(windows)]
const UV_TARGET: &str = "unknown-linux-gnu";
#[cfg(windows)]
const UV_SHA256: [(&str, &str); 2] = [
    (
        "aarch64",
        "5231be65f496304623895dacdbf1de8504fec90303684bdf05805aa34414dd21",
    ),
    (
        "x86_64",
        "b4dfaef47d491a7296981f8374a4595f55dbf84e8937c8ecd2983574d8bb3da6",
    ),
];

/// Where in WSL's home the app puts the uv it downloads: where uv's own installer would, since
/// the app's data directory on Windows is out of WSL's reach.
#[cfg(windows)]
const OWN_UV: &str = ".local/bin";

/// Runs `$@`, uv, in WSL so that `wsl.exe` killed, as quitting does, stops it as on a Mac. The
/// hangup goes to this shell alone, which interrupts uv as Ctrl+C would, and kills it where it
/// has not stopped in time. uv runs as a job of its own, so that an interrupt is not ignored, and
/// says what it says into a file, followed from there, which no hangup closes.
#[cfg(windows)]
const INTERRUPTIBLE: &str = r#"said=$(mktemp) || exit
set -m
"$@" 2>"$said" & uv=$!
set +m
tail -n +1 -f --pid="$uv" "$said" >&2 &
exec 2>/dev/null
trap 'kill -INT "$uv"; sleep 3; kill -KILL "$uv"' HUP
while wait "$uv"; status=$?; kill -0 "$uv"; do :; done
wait
rm -f "$said"
exit "$status""#;

/// What an install that failed says first where there is no WSL to install in: the app's page
/// shows it as such.
#[cfg(windows)]
const NO_WSL: &str = "WSL missing";

/// How long WSL may take to start, its virtual machine with it.
#[cfg(windows)]
const WAKING: Duration = Duration::from_secs(60);

/// The most a uv archive may weigh, and how long its download may take: to connect, and in all.
const UV_LIMIT: u64 = 64 << 20;
const UV_CONNECT: Duration = Duration::from_secs(30);
const UV_TIMEOUT: Duration = Duration::from_secs(30 * 60);

/// How long `hmz` or uv may take to say its version, its help or a directory. The first after
/// an install compiles what it imports.
const ASKING: Duration = Duration::from_secs(20);

/// The Pythons hmz runs on: `requires-python` in pyproject.toml.
const PYTHON: &str = ">=3.12";

/// How much of what an install said is kept to show where it fails, from its end.
const KEPT_LINES: usize = 12;

/// What is being done, as the app's own page shows it.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Step {
    Uv,
    Python,
    Hmz,
}

/// An install under way: whether it replaces an `hmz`, its step, and the last line uv said.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Progress {
    pub updating: bool,
    pub step: Step,
    pub line: String,
}

/// An install that did not happen: what was said, and whether the `hmz` already there can be
/// kept instead -- one that takes `web --attached`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Failed {
    pub updating: bool,
    pub said: String,
    pub keep: bool,
}

/// What `choose` is asked to do.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum How {
    /// Install where the `hmz` is not the app's version and no epics of it are running.
    Usual,
    /// Install where it is not the app's version, epics or not.
    Now,
    /// Install nothing: the `hmz` there, whatever its version.
    Keep,
}

/// The `hmz` to run.
#[derive(Debug, PartialEq)]
pub enum Chosen {
    Ready(PathBuf),
    /// Of this other version, kept while the epics it holds run.
    Held(PathBuf, String),
    /// None, where nothing installs one: `HUMANIZE_HMZ` is set, or the app is a development
    /// build.
    Missing,
}

/// What is to be done with the `hmz` there.
#[derive(Debug, PartialEq)]
pub enum Plan {
    Use,
    Install,
    /// Kept as it is: an install would pull it from under the epics it runs.
    Defer,
}

/// The decision: an `hmz` of the app's version is used, and any other -- older, newer, or one
/// that cannot say -- replaced by it, unless epics are running in it.
pub fn plan(installed: Option<&str>, pinned: &str, busy: bool) -> Plan {
    match installed {
        Some(installed) if installed == pinned => Plan::Use,
        _ if busy => Plan::Defer,
        _ => Plan::Install,
    }
}

/// The `hmz` to run, installed or replaced first where it must be, telling how that goes.
pub fn choose(
    env: &Env,
    data: &Path,
    version: &str,
    how: How,
    tell: &dyn Fn(Progress),
) -> Result<Chosen, Failed> {
    #[cfg(windows)]
    wsl().map_err(|why| Failed {
        updating: false,
        said: format!("{NO_WSL}: {why}"),
        keep: false,
    })?;
    let named = env
        .get(OsStr::new(server::OVERRIDE))
        .is_some_and(|named| !named.is_empty());
    let Some(pinned) = pep440(version).filter(|_| !named) else {
        return Ok(server::find(env).map_or(Chosen::Missing, Chosen::Ready));
    };
    let failed = |said| Failed {
        updating: false,
        said,
        keep: false,
    };
    let (uv, bin) = match uvs(env, data).iter().find_map(|uv| answers(uv, env)) {
        Some(found) => found,
        None => {
            let getting = |line: &str| {
                tell(Progress {
                    updating: false,
                    step: Step::Uv,
                    line: line.to_owned(),
                })
            };
            getting(&format!("uv {UV}"));
            let uv = download(env, &own(env, data), &getting).map_err(failed)?;
            answers(&uv, env).ok_or_else(|| failed(format!("{} did not answer", uv.display())))?
        }
    };
    let hmz = joined(&bin, "hmz");
    if how == How::Keep {
        return Ok(Chosen::Ready(hmz));
    }
    let updating = server::runnable(&hmz);
    let installed = updating.then(|| version_of(&hmz, env)).flatten();
    // Asked only where it decides anything: there is an `hmz` to replace.
    let busy =
        how == How::Usual && updating && installed.as_deref() != Some(pinned.as_str()) && busy(env);
    match plan(installed.as_deref(), &pinned, busy) {
        Plan::Use => Ok(Chosen::Ready(hmz)),
        Plan::Defer => {
            let installed = installed.unwrap_or_default();
            log::info!("hmz {installed} holds running epics; hmz {pinned} waits for them");
            Ok(Chosen::Held(hmz, installed))
        }
        Plan::Install => {
            log::info!("installing hmz {pinned} with {}", uv.display());
            let progress = |step, line: &str| {
                tell(Progress {
                    updating,
                    step,
                    line: line.to_owned(),
                })
            };
            match install(&uv, &hmz, env, &pinned, &progress) {
                Ok(()) => Ok(Chosen::Ready(hmz)),
                Err(said) => {
                    log::warn!("hmz {pinned} was not installed: {said}");
                    Err(Failed {
                        updating,
                        said,
                        keep: attached(&hmz, env),
                    })
                }
            }
        }
    }
}

/// The PEP 440 version of the app's SemVer one, as PyPI has the same release: `0.5.0-rc.1` is
/// `0.5.0rc1`. None for a development build's `0.0.0`, and for what is no release.
pub fn pep440(semver: &str) -> Option<String> {
    let semver = semver.split('+').next().unwrap_or_default();
    let (release, pre) = match semver.split_once('-') {
        Some((release, pre)) => (release, Some(pre)),
        None => (semver, None),
    };
    let numbers: Vec<u64> = release
        .split('.')
        .map(|n| n.parse().ok())
        .collect::<Option<_>>()?;
    if numbers.len() != 3 || numbers == [0, 0, 0] {
        return None;
    }
    let mut version = format!("{}.{}.{}", numbers[0], numbers[1], numbers[2]);
    if let Some(pre) = pre {
        let n = pre.trim_start_matches(|c: char| !c.is_ascii_digit());
        let kind = match pre[..pre.len() - n.len()].trim_end_matches('.') {
            "alpha" | "a" => "a",
            "beta" | "b" => "b",
            "rc" | "c" => "rc",
            _ => return None,
        };
        let n: u64 = if n.is_empty() { 0 } else { n.parse().ok()? };
        version.push_str(&format!("{kind}{n}"));
    }
    Some(version)
}

/// The version `hmz --version` says: `hmz 0.5.0rc1`, wherever among what else it printed.
pub fn said_version(out: &str) -> Option<String> {
    out.lines().find_map(|line| {
        let mut words = line.split_whitespace();
        let version = (words.next()? == "hmz").then(|| words.next())??;
        version
            .starts_with(|c: char| c.is_ascii_digit())
            .then(|| version.to_owned())
    })
}

/// Where to look for uv, each place once: `PATH`, the places its installers put it, and the
/// app's own.
pub fn uvs(env: &Env, data: &Path) -> Vec<PathBuf> {
    let home = shell_env::home(env);
    let path = env.get(OsStr::new("PATH")).map(|path| split(path));
    let dirs = path.into_iter().flatten().filter(|dir| dir.has_root());
    let mut uvs: Vec<PathBuf> = Vec::new();
    for dir in dirs.chain([
        joined(&home, ".local/bin"),
        joined(&home, ".cargo/bin"),
        "/opt/homebrew/bin".into(),
        own(env, data),
    ]) {
        let uv = joined(&dir, "uv");
        if !uvs.contains(&uv) {
            uvs.push(uv);
        }
    }
    uvs
}

/// The directories in a `PATH`: on Windows WSL's, split as Linux splits it.
#[cfg(unix)]
fn split(path: &OsStr) -> Vec<PathBuf> {
    std::env::split_paths(path).collect()
}

#[cfg(windows)]
fn split(path: &OsStr) -> Vec<PathBuf> {
    path.to_string_lossy()
        .split(':')
        .map(PathBuf::from)
        .collect()
}

/// `name` in `dir`: on Windows a path in WSL, joined as Linux joins it.
#[cfg(unix)]
fn joined(dir: &Path, name: &str) -> PathBuf {
    dir.join(name)
}

#[cfg(windows)]
fn joined(dir: &Path, name: &str) -> PathBuf {
    format!("{}/{name}", dir.to_string_lossy().trim_end_matches('/')).into()
}

/// Where the app keeps the uv it downloads.
#[cfg(unix)]
fn own(_env: &Env, data: &Path) -> PathBuf {
    data.join("uv")
}

#[cfg(windows)]
fn own(env: &Env, _data: &Path) -> PathBuf {
    joined(&shell_env::home(env), OWN_UV)
}

/// A program run as the app runs it, in the login shell's environment alone: on Windows, in WSL.
#[cfg(unix)]
fn command(program: &Path, env: &Env) -> Command {
    let mut command = Command::new(program);
    command.env_clear().envs(env);
    command
}

#[cfg(windows)]
fn command(program: &Path, env: &Env) -> Command {
    crate::wsl::command(program, Some(env))
}

/// uv, as it is run to install.
#[cfg(unix)]
fn installing(uv: &Path, env: &Env) -> Command {
    command(uv, env)
}

#[cfg(windows)]
fn installing(uv: &Path, env: &Env) -> Command {
    let mut command = crate::wsl::command("/bin/sh", Some(env));
    command.args(["-c", INTERRUPTIBLE, "sh"]).arg(uv);
    command
}

/// Whether there is a WSL to install in: `wsl.exe`, and a distribution it starts.
#[cfg(windows)]
fn wsl() -> Result<(), String> {
    let mut command = crate::wsl::command("true", None);
    // What `wsl.exe` says of itself in UTF-8, not UTF-16.
    command
        .env("WSL_UTF8", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let child =
        child::spawn(&mut command).map_err(|why| format!("wsl.exe could not be run: {why}"))?;
    let reading = |out: Option<Box<dyn Read + Send>>| {
        std::thread::spawn(move || {
            let mut said = String::new();
            if let Some(mut out) = out {
                let _ = out.read_to_string(&mut said);
            }
            said
        })
    };
    let out = reading(child.take_stdout().map(|out| Box::new(out) as _));
    let err = reading(child.take_stderr().map(|err| Box::new(err) as _));
    let status = child.wait_timeout(WAKING);
    if !matches!(status, Ok(Some(_))) {
        let _ = child.kill();
        let _ = child.wait();
    }
    let said = [out, err]
        .map(|said| said.join().unwrap_or_default())
        .concat();
    match status {
        Ok(Some(status)) if status.success() => Ok(()),
        _ if !said.trim().is_empty() => Err(said.trim().to_owned()),
        Ok(Some(status)) => Err(format!("wsl.exe exited: {status}")),
        Ok(None) => Err(format!("WSL did not start in {} s", WAKING.as_secs())),
        Err(why) => Err(format!("wsl.exe could not be waited for: {why}")),
    }
}

/// A uv, and where it puts tools' programs, where it is there and says so: one too old to know
/// `uv tool` does not.
fn answers(uv: &Path, env: &Env) -> Option<(PathBuf, PathBuf)> {
    if !server::runnable(uv) {
        return None;
    }
    let bin = asked(uv, ["tool", "dir", "--bin"], env)?;
    let bin = PathBuf::from(bin.trim());
    bin.has_root().then(|| (uv.to_owned(), bin))
}

/// What `hmz --version` says it is.
fn version_of(hmz: &Path, env: &Env) -> Option<String> {
    said_version(&asked(hmz, ["--version"], env)?)
}

/// Whether an `hmz` takes `web --attached`, which the app runs it with.
fn attached(hmz: &Path, env: &Env) -> bool {
    server::runnable(hmz)
        && asked(hmz, ["web", "--help"], env).is_some_and(|h| h.contains("--attached"))
}

/// What a program prints, where it exits well in time.
fn asked<const N: usize>(program: &Path, args: [&str; N], env: &Env) -> Option<String> {
    let mut command = command(program, env);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    let child = child::spawn(&mut command).ok()?;
    let mut stdout = child.take_stdout()?;
    // Read as it is written, so a long answer cannot fill the pipe and stall it.
    let reading = std::thread::spawn(move || {
        let mut out = String::new();
        stdout.read_to_string(&mut out).map(|_| out)
    });
    let status = match child.wait_timeout(ASKING) {
        Ok(Some(status)) => status,
        _ => {
            log::warn!("{} did not answer in time", program.display());
            let _ = child.kill();
            let _ = child.wait();
            return None;
        }
    };
    let out = reading.join().ok()?.ok()?;
    status.success().then_some(out)
}

/// Whether this machine's daemon is running: it holds a workspace's epics, or is about to let go.
/// What a daemon writes beside its socket -- `daemon.json` in `humanize-<uid>` in the temporary
/// directory -- names its process.
#[cfg(unix)]
pub fn busy(env: &Env) -> bool {
    let tmp = env
        .get(OsStr::new("TMPDIR"))
        .filter(|tmp| !tmp.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    // SAFETY: `getuid` cannot fail.
    let uid = unsafe { libc::getuid() };
    let record = tmp.join(format!("humanize-{uid}/daemon.json"));
    let pid = fs::read(record)
        .ok()
        .and_then(|said| serde_json::from_slice::<serde_json::Value>(&said).ok())
        .and_then(|said| said.get("pid")?.as_i64())
        .and_then(|pid| libc::pid_t::try_from(pid).ok())
        .filter(|&pid| pid > 0);
    pid.is_some_and(alive)
}

#[cfg(unix)]
fn alive(pid: libc::pid_t) -> bool {
    // SAFETY: signal 0 checks the process is there, and sends nothing.
    (unsafe { libc::kill(pid, 0) }) == 0
        || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

/// On Windows, WSL's daemon: its record read, and its process looked for, in WSL.
#[cfg(windows)]
pub fn busy(env: &Env) -> bool {
    let sh = Path::new("/bin/sh");
    let record = r#"cat "${TMPDIR:-/tmp}/humanize-$(id -u)/daemon.json""#;
    let pid = asked(sh, ["-c", record], env)
        .and_then(|said| serde_json::from_str::<serde_json::Value>(&said).ok())
        .and_then(|said| said.get("pid")?.as_i64())
        .and_then(|pid| i32::try_from(pid).ok())
        .filter(|&pid| pid > 0);
    pid.is_some_and(|pid| {
        asked(sh, ["-c", r#"kill -0 "$1""#, "sh", &pid.to_string()], env).is_some()
    })
}

/// `uv tool install --force hmz==<pinned>`, keeping the extras it was installed with, telling
/// each line uv says; then checks the `hmz` there is that version.
fn install(
    uv: &Path,
    hmz: &Path,
    env: &Env,
    pinned: &str,
    tell: &dyn Fn(Step, &str),
) -> Result<(), String> {
    tell(Step::Hmz, "");
    let extras = extras(hmz, env);
    let wanted = if extras.is_empty() {
        format!("hmz=={pinned}")
    } else {
        format!("hmz[{}]=={pinned}", extras.join(","))
    };
    let mut command = installing(uv, env);
    command
        .args(["tool", "install", "--force"])
        // A Python hmz runs on, downloaded where there is none: uv would take the first found,
        // and a Mac's own is 3.9.
        .args(["--python", PYTHON])
        // Asked of the index again: a release this new may be missing from what uv has cached.
        .args(["--refresh-package", "hmz"])
        .arg(&wanted)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    // In WSL, `wsl.exe` starts it in its home already.
    #[cfg(unix)]
    command.current_dir(shell_env::home(env));
    // Interrupted as the app quits, which uv takes as Ctrl+C: what it installs is put in place
    // whole or not at all.
    let child = child::spawn(&mut command)
        .map_err(|why| format!("{} could not be run: {why}", uv.display()))?;
    let mut kept: Vec<String> = Vec::new();
    if let Some(stderr) = child.take_stderr() {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            log::info!("uv: {line}");
            tell(step(line), line.trim_start_matches("+ "));
            if kept.len() == KEPT_LINES {
                kept.remove(0);
            }
            kept.push(line.to_owned());
        }
    }
    let status = child.wait();
    let said = kept.join("\n");
    match status {
        Ok(status) if status.success() => {}
        _ if !said.is_empty() => return Err(said),
        Ok(status) => return Err(format!("uv exited: {status}")),
        Err(why) => return Err(format!("uv could not be waited for: {why}")),
    }
    match version_of(hmz, env) {
        Some(version) if version == pinned => Ok(()),
        found => Err(format!(
            "uv installed {wanted}, but {} says it is {}",
            hmz.display(),
            found.as_deref().unwrap_or("nothing")
        )),
    }
}

/// Which step a line uv says is part of: getting Python, or the rest.
fn step(line: &str) -> Step {
    if line.contains("cpython") || line.contains("Python 3") {
        Step::Python
    } else {
        Step::Hmz
    }
}

/// The extras an `hmz` was installed with, as uv wrote them in the receipt beside its
/// environment: `requirements = [{ name = "hmz", extras = ["all"], ... }]`, on one line or one
/// requirement a line.
#[cfg(unix)]
fn extras(hmz: &Path, _env: &Env) -> Vec<String> {
    let receipt = fs::canonicalize(hmz)
        .ok()
        .and_then(|real| Some(real.parent()?.parent()?.join("uv-receipt.toml")))
        .and_then(|receipt| fs::read_to_string(receipt).ok())
        .unwrap_or_default();
    receipt_extras(&receipt)
}

#[cfg(windows)]
fn extras(hmz: &Path, env: &Env) -> Vec<String> {
    let receipt = r#"cat "$(dirname "$(dirname "$(readlink -f "$1")")")/uv-receipt.toml""#;
    let hmz = hmz.to_string_lossy();
    let receipt = asked(Path::new("/bin/sh"), ["-c", receipt, "sh", &hmz], env);
    receipt_extras(&receipt.unwrap_or_default())
}

fn receipt_extras(receipt: &str) -> Vec<String> {
    // hmz's own table, up to where it closes: what follows it is another requirement's.
    let listed = receipt
        .split_once("requirements = [")
        .and_then(|(_, requirements)| requirements.split_once(r#"{ name = "hmz""#))
        .and_then(|(_, hmz)| hmz.split_once('}'))
        .and_then(|(hmz, _)| hmz.split_once("extras = [")?.1.split_once(']'));
    let Some((listed, _)) = listed else {
        return Vec::new();
    };
    listed
        .split(',')
        .map(|extra| extra.trim().trim_matches('"'))
        .filter(|extra| {
            !extra.is_empty()
                && extra
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
        })
        .map(str::to_owned)
        .collect()
}

/// The uv of `UV` for this Mac's architecture -- on Windows, WSL's -- from its GitHub release
/// into `dir`, checked against the sum pinned here.
fn download(env: &Env, dir: &Path, tell: &dyn Fn(&str)) -> Result<PathBuf, String> {
    #[cfg(unix)]
    let arch = std::env::consts::ARCH;
    #[cfg(windows)]
    let arch = asked(Path::new("uname"), ["-m"], env).unwrap_or_default();
    let arch = arch.trim();
    let sum = UV_SHA256
        .iter()
        .find(|(of, _)| *of == arch)
        .map(|(_, sum)| *sum)
        .ok_or_else(|| format!("no uv for {arch}"))?;
    let url = format!(
        "https://github.com/astral-sh/uv/releases/download/{UV}/uv-{arch}-{UV_TARGET}.tar.gz"
    );
    log::info!("downloading {url}");
    // Through the proxy the login shell names, as uv and everything run from a terminal would.
    let proxy = ["HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"]
        .iter()
        .find_map(|name| {
            env.get(OsStr::new(name))?
                .to_str()
                .filter(|p| !p.is_empty())
        })
        .and_then(|proxy| {
            ureq::Proxy::new(proxy)
                .inspect_err(|why| log::warn!("the proxy {proxy} is not one: {why}"))
                .ok()
        });
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_connect(Some(UV_CONNECT))
        .timeout_global(Some(UV_TIMEOUT))
        .proxy(proxy)
        // What the system trusts, a company's own authority in the keychain or store included.
        .tls_config(
            ureq::tls::TlsConfig::builder()
                .root_certs(ureq::tls::RootCerts::PlatformVerifier)
                .build(),
        )
        .build()
        .into();
    let failed =
        |why: &dyn std::fmt::Display| format!("uv could not be downloaded from {url}: {why}");
    let mut got = agent.get(&url).call().map_err(|why| failed(&why))?;
    let size = got.body().content_length().filter(|&size| size <= UV_LIMIT);
    let mut body = got.body_mut().with_config().limit(UV_LIMIT).reader();
    let mut archive = Vec::with_capacity(size.unwrap_or_default() as usize);
    let mut chunk = vec![0; 256 << 10];
    let mut told = String::new();
    loop {
        let n = body.read(&mut chunk).map_err(|why| failed(&why))?;
        if n == 0 {
            break;
        }
        archive.extend_from_slice(&chunk[..n]);
        let mb = |bytes: usize| bytes as f64 / 1e6;
        let line = match size {
            Some(size) => format!(
                "uv {UV}, {:.1} of {:.1} MB",
                mb(archive.len()),
                mb(size as usize)
            ),
            None => format!("uv {UV}, {:.1} MB", mb(archive.len())),
        };
        // Told only as it changes, a tenth of a megabyte at a time.
        if line != told {
            tell(&line);
            told = line;
        }
    }
    unpack(&archive, sum, dir)
}

/// The `uv` in a release archive, once its sha256 is the one expected.
pub fn unpacked(archive: &[u8], sha256: &str) -> Result<Vec<u8>, String> {
    let sum = format!("{:x}", Sha256::digest(archive));
    if sum != sha256 {
        return Err(format!(
            "the uv downloaded is not uv {UV}: its sha256 is {sum}"
        ));
    }
    let broken = |why: std::io::Error| format!("uv could not be unpacked: {why}");
    let mut entries = tar::Archive::new(GzDecoder::new(archive));
    for entry in entries.entries().map_err(broken)? {
        let mut entry = entry.map_err(broken)?;
        if entry.path().map_err(broken)?.file_name() != Some(OsStr::new("uv")) {
            continue;
        }
        let mut uv = Vec::new();
        entry.read_to_end(&mut uv).map_err(broken)?;
        return Ok(uv);
    }
    Err("the uv archive holds no uv".into())
}

/// The `uv` in a release archive, once its sha256 is the one expected, written into `dir`
/// whole and then moved into place.
#[cfg(unix)]
pub fn unpack(archive: &[u8], sha256: &str, dir: &Path) -> Result<PathBuf, String> {
    let unpacked = unpacked(archive, sha256)?;
    let broken = |why: std::io::Error| format!("uv could not be unpacked: {why}");
    fs::create_dir_all(dir).map_err(broken)?;
    let uv = dir.join("uv");
    let beside = dir.join(format!(".uv.{}.new", std::process::id()));
    let written = fs::write(&beside, unpacked)
        .and_then(|()| fs::set_permissions(&beside, fs::Permissions::from_mode(0o755)))
        .and_then(|()| fs::rename(&beside, &uv));
    if let Err(why) = written {
        let _ = fs::remove_file(&beside);
        return Err(broken(why));
    }
    Ok(uv)
}

/// Writes what it reads to `uv` in `$1` in WSL: beside it first, and moved into place once its
/// sha256 is `$2`, so it is never there half written -- `wsl.exe` killed ends what it reads.
#[cfg(windows)]
const WRITE: &str = r#"mkdir -p "$1" && new="$1/.uv.$$.new" || exit
trap 'rm -f "$new"; exit 1' HUP INT TERM
cat > "$new" && echo "$2  $new" | sha256sum -c --status && chmod 755 "$new" &&
mv -f "$new" "$1/uv" || { rm -f "$new"; exit 1; }"#;

/// On Windows, into `dir` in WSL.
#[cfg(windows)]
pub fn unpack(archive: &[u8], sha256: &str, dir: &Path) -> Result<PathBuf, String> {
    let unpacked = unpacked(archive, sha256)?;
    let mut command = crate::wsl::command("/bin/sh", None);
    command
        .args(["-c", WRITE, "sh"])
        .arg(dir)
        .arg(format!("{:x}", Sha256::digest(&unpacked)))
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    let broken = |why: &dyn std::fmt::Display| format!("uv could not be written into WSL: {why}");
    let child = child::spawn(&mut command).map_err(|why| broken(&why))?;
    if let Some(mut stdin) = child.take_stdin() {
        // Where it fails, `sh` says why.
        let _ = stdin.write_all(&unpacked);
    }
    let mut said = String::new();
    if let Some(mut stderr) = child.take_stderr() {
        let _ = stderr.read_to_string(&mut said);
    }
    match child.wait() {
        Ok(status) if status.success() => Ok(joined(dir, "uv")),
        _ if !said.trim().is_empty() => Err(broken(&said.trim())),
        Ok(status) => Err(broken(&status)),
        Err(why) => Err(broken(&why)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use crate::lock;
    #[cfg(unix)]
    use std::sync::Mutex as Lock;

    #[test]
    fn says_a_semver_release_as_pypi_does() {
        assert_eq!(pep440("0.5.0").as_deref(), Some("0.5.0"));
        assert_eq!(pep440("0.5.0-rc.1").as_deref(), Some("0.5.0rc1"));
        assert_eq!(pep440("1.2.3-alpha.4").as_deref(), Some("1.2.3a4"));
        assert_eq!(pep440("1.2.3-beta.12").as_deref(), Some("1.2.3b12"));
        assert_eq!(pep440("0.1.0-beta.1+build.7").as_deref(), Some("0.1.0b1"));
        assert_eq!(pep440("1.0.0-rc1").as_deref(), Some("1.0.0rc1"));
        assert_eq!(pep440("0.0.0"), None);
        for nothing in ["", "1.2", "1.2.3.4", "x.1.2", "1.2.3-dev.1", "1.2.3-rc.x"] {
            assert_eq!(pep440(nothing), None, "{nothing}");
        }
    }

    #[test]
    fn reads_the_version_hmz_says() {
        assert_eq!(said_version("hmz 0.5.0\n").as_deref(), Some("0.5.0"));
        assert_eq!(
            said_version("warning: something\nhmz 0.5.0rc1\n").as_deref(),
            Some("0.5.0rc1")
        );
        assert_eq!(said_version("hmz\n"), None);
        assert_eq!(said_version("hmz: error: unknown\n"), None);
        assert_eq!(said_version("hmz version\n"), None);
        assert_eq!(said_version(""), None);
    }

    #[test]
    fn decides_what_to_do_with_the_hmz_there() {
        // Missing or saying no version, older, newer, equal; then each with epics running, which
        // are asked after only where there is an `hmz`.
        assert_eq!(plan(None, "0.5.0", false), Plan::Install);
        assert_eq!(plan(Some("0.4.0"), "0.5.0", false), Plan::Install);
        assert_eq!(plan(Some("0.6.0"), "0.5.0", false), Plan::Install);
        assert_eq!(plan(Some("0.5.0"), "0.5.0", false), Plan::Use);
        assert_eq!(plan(None, "0.5.0", true), Plan::Defer);
        assert_eq!(plan(Some("0.4.0"), "0.5.0", true), Plan::Defer);
        assert_eq!(plan(Some("0.6.0"), "0.5.0", true), Plan::Defer);
        assert_eq!(plan(Some("0.5.0"), "0.5.0", true), Plan::Use);
    }

    #[cfg(unix)]
    #[test]
    fn looks_for_uv_along_path_then_where_installers_put_it() {
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b:/opt/homebrew/bin".into()),
            ("HOME".into(), "/Users/u".into()),
        ]);
        let data = Path::new("/data");
        let found: Vec<PathBuf> = uvs(&env, data);
        let expected: Vec<PathBuf> = [
            "/a/uv",
            "/b/uv",
            "/opt/homebrew/bin/uv",
            "/Users/u/.local/bin/uv",
            "/Users/u/.cargo/bin/uv",
            "/data/uv/uv",
        ]
        .map(PathBuf::from)
        .into();
        assert_eq!(found, expected);
    }

    #[cfg(windows)]
    #[test]
    fn looks_for_uv_along_wsls_path_then_where_installers_put_it() {
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b/:/opt/homebrew/bin".into()),
            ("HOME".into(), "/home/u".into()),
        ]);
        let found: Vec<PathBuf> = uvs(&env, Path::new(r"C:\data"));
        let expected: Vec<PathBuf> = [
            "/a/uv",
            "/b/uv",
            "/opt/homebrew/bin/uv",
            "/home/u/.local/bin/uv",
            "/home/u/.cargo/bin/uv",
        ]
        .map(PathBuf::from)
        .into();
        assert_eq!(found, expected);
    }

    #[test]
    fn reads_the_extras_from_uvs_receipt() {
        let receipt = r#"[tool]
requirements = [{ name = "hmz", extras = ["all", "kimi"], specifier = "==0.1.0" }]
entrypoints = [
    { name = "hmz", install-path = "/x/bin/hmz", from = "hmz" },
]
"#;
        assert_eq!(receipt_extras(receipt), ["all", "kimi"]);
        // One requirement a line, as uv writes them with `--with`.
        let receipt = r#"[tool]
requirements = [
    { name = "hmz", extras = ["dsh"] },
    { name = "rich", extras = ["jupyter"] },
]
"#;
        assert_eq!(receipt_extras(receipt), ["dsh"]);
        let receipt = r#"requirements = [{ name = "hmz" }, { name = "rich", extras = ["x"] }]"#;
        assert!(receipt_extras(receipt).is_empty());
        assert!(receipt_extras(r#"requirements = [{ name = "hmz" }]"#).is_empty());
        assert!(
            receipt_extras(r#"requirements = [{ name = "hmz", extras = ["$(x)"] }]"#).is_empty()
        );
        assert!(receipt_extras("").is_empty());
    }

    /// A gzipped tar holding `name`, as uv's release archives hold it.
    fn archive(name: &str, body: &[u8]) -> Vec<u8> {
        let mut tar = tar::Builder::new(flate2::write::GzEncoder::new(
            Vec::new(),
            flate2::Compression::fast(),
        ));
        let mut header = tar::Header::new_gnu();
        header.set_size(body.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        tar.append_data(&mut header, name, body).unwrap();
        tar.into_inner().unwrap().finish().unwrap()
    }

    #[test]
    fn takes_uv_from_an_archive_only_where_its_sum_is_the_pinned_one() {
        let good = archive("uv-x86_64-unknown-linux-gnu/uv", b"#!/bin/sh\n");
        let sum = format!("{:x}", Sha256::digest(&good));
        assert_eq!(unpacked(&good, &sum).unwrap(), b"#!/bin/sh\n");
        let tampered = archive("uv-x86_64-unknown-linux-gnu/uv", b"#!/bin/sh\nevil\n");
        let refused = unpacked(&tampered, &sum).unwrap_err();
        assert!(refused.contains("sha256"), "{refused}");
        let empty = archive("uv-x86_64-unknown-linux-gnu/uvx", b"");
        let sum = format!("{:x}", Sha256::digest(&empty));
        assert!(unpacked(&empty, &sum).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn unpacks_uv_only_where_its_sum_is_the_pinned_one() {
        let dir = tempfile::tempdir().unwrap();
        let good = archive("uv-aarch64-apple-darwin/uv", b"#!/bin/sh\n");
        let sum = format!("{:x}", Sha256::digest(&good));
        let uv = unpack(&good, &sum, dir.path()).unwrap();
        assert_eq!(uv, dir.path().join("uv"));
        assert_eq!(fs::read(&uv).unwrap(), b"#!/bin/sh\n");
        assert!(server::runnable(&uv));

        let tampered = archive("uv-aarch64-apple-darwin/uv", b"#!/bin/sh\nevil\n");
        let refused = unpack(&tampered, &sum, dir.path()).unwrap_err();
        assert!(refused.contains("sha256"), "{refused}");
        assert_eq!(fs::read(&uv).unwrap(), b"#!/bin/sh\n");

        let empty = archive("uv-aarch64-apple-darwin/uvx", b"");
        let sum = format!("{:x}", Sha256::digest(&empty));
        assert!(unpack(&empty, &sum, dir.path()).is_err());
        // Nothing half-written is left beside it.
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn pins_a_sum_for_each_architecture() {
        assert_eq!(UV_SHA256.map(|(arch, _)| arch), ["aarch64", "x86_64"]);
        for (arch, sum) in UV_SHA256 {
            assert!(["aarch64", "x86_64"].contains(&arch));
            assert_eq!(sum.len(), 64);
            assert!(sum.chars().all(|c| c.is_ascii_hexdigit()));
        }
    }

    #[cfg(windows)]
    #[test]
    fn joins_wsls_paths_as_linux_does() {
        assert_eq!(
            joined(Path::new("/home/u"), "uv"),
            PathBuf::from("/home/u/uv")
        );
        assert_eq!(
            joined(Path::new("/home/u/"), "uv"),
            PathBuf::from("/home/u/uv")
        );
        assert_eq!(
            split(OsStr::new("/usr/bin:/bin")),
            [PathBuf::from("/usr/bin"), PathBuf::from("/bin")]
        );
    }

    #[cfg(unix)]
    #[test]
    fn tells_a_daemon_running_from_none() {
        let tmp = tempfile::tempdir().unwrap();
        let env = Env::from([("TMPDIR".into(), tmp.path().into())]);
        assert!(!busy(&env));
        let dir = tmp
            .path()
            .join(format!("humanize-{}", unsafe { libc::getuid() }));
        fs::create_dir_all(&dir).unwrap();
        let record =
            |pid: &str| fs::write(dir.join("daemon.json"), format!(r#"{{"pid": {pid}}}"#)).unwrap();
        record(&std::process::id().to_string());
        assert!(busy(&env));
        // A pid no process has: gone without taking its record along.
        record("2147483646");
        assert!(!busy(&env));
        record("\"x\"");
        assert!(!busy(&env));
    }

    /// A stand-in for uv: `tool dir --bin` names `$FAKE_BIN`, and `tool install` writes down
    /// what it was asked and puts there an `hmz` saying the version asked for -- or fails, as
    /// `$FAKE` says.
    #[cfg(unix)]
    const FAKE_UV: &str = r#"#!/bin/sh
case "$1 $2" in
  "tool dir") echo "$FAKE_BIN" ;;
  "tool install")
    echo "$@" >> "$FAKE_BIN/../argv"
    if [ "$FAKE" = slow ]; then
      echo $$ > "$FAKE_BIN/../pid"
      exec sleep 60
    fi
    if [ "$FAKE" = offline ]; then
      echo "error: Failed to fetch: https://pypi.org/simple/hmz/" >&2
      exit 2
    fi
    echo "Downloading cpython-3.13.7-macos-aarch64-none (download) (17.6MiB)" >&2
    echo "Resolved 30 packages in 5ms" >&2
    for wanted; do :; done
    version="${wanted#*==}"
    [ "$FAKE" = wrong ] && version=9.9.9
    mkdir -p "$FAKE_BIN"
    printf '#!/bin/sh\n[ "$1" = --version ] && echo "hmz %s"\n[ "$1 $2" = "web --help" ] && echo --attached\nexit 0\n' "$version" > "$FAKE_BIN/hmz"
    chmod +x "$FAKE_BIN/hmz"
    echo "Installed 1 executable: hmz" >&2 ;;
  *) exit 2 ;;
esac
"#;

    #[cfg(unix)]
    struct Fake {
        dir: tempfile::TempDir,
        env: Env,
    }

    #[cfg(unix)]
    impl Fake {
        fn new(mode: &str) -> Self {
            let dir = tempfile::tempdir().unwrap();
            let tools = dir.path().join("tools");
            fs::create_dir_all(tools.join("bin")).unwrap();
            let uv = tools.join("uv");
            fs::write(&uv, FAKE_UV).unwrap();
            fs::set_permissions(&uv, fs::Permissions::from_mode(0o755)).unwrap();
            let env = Env::from([
                (
                    "PATH".into(),
                    format!("{}:/usr/bin:/bin", tools.display()).into(),
                ),
                ("HOME".into(), dir.path().into()),
                ("TMPDIR".into(), dir.path().into()),
                ("FAKE_BIN".into(), tools.join("bin").into()),
                ("FAKE".into(), mode.into()),
            ]);
            Self { dir, env }
        }

        fn hmz(&self) -> PathBuf {
            self.dir.path().join("tools/bin/hmz")
        }

        fn argv(&self) -> String {
            fs::read_to_string(self.dir.path().join("tools/argv")).unwrap_or_default()
        }

        /// An `hmz` already there, of this version.
        fn installed(&self, version: &str) {
            fs::write(
                self.hmz(),
                format!("#!/bin/sh\n[ \"$1\" = --version ] && echo \"hmz {version}\"\nexit 0\n"),
            )
            .unwrap();
            fs::set_permissions(self.hmz(), fs::Permissions::from_mode(0o755)).unwrap();
        }

        fn choose(&self, version: &str, how: How) -> (Result<Chosen, Failed>, Vec<Progress>) {
            let told = Lock::new(Vec::new());
            let data = self.dir.path().join("data");
            let chosen = choose(&self.env, &data, version, how, &|p| lock(&told).push(p));
            (chosen, told.into_inner().unwrap())
        }
    }

    #[cfg(unix)]
    #[test]
    fn installs_the_apps_own_version_with_uv() {
        let fake = Fake::new("ok");
        let (chosen, told) = fake.choose("0.5.0-rc.1", How::Usual);
        assert_eq!(chosen, Ok(Chosen::Ready(fake.hmz())));
        assert_eq!(
            fake.argv(),
            "tool install --force --python >=3.12 --refresh-package hmz hmz==0.5.0rc1\n"
        );
        assert!(told.iter().all(|p| !p.updating));
        let steps: Vec<Step> = told.iter().map(|p| p.step).collect();
        assert_eq!(steps.first(), Some(&Step::Hmz));
        assert!(steps.contains(&Step::Python));
        assert_eq!(told.last().unwrap().line, "Installed 1 executable: hmz");

        // Right as it is: nothing installed again.
        let (chosen, told) = fake.choose("0.5.0-rc.1", How::Usual);
        assert_eq!(chosen, Ok(Chosen::Ready(fake.hmz())));
        assert!(told.is_empty());
        assert_eq!(fake.argv().lines().count(), 1);
    }

    #[cfg(unix)]
    #[test]
    fn replaces_another_version_unless_its_epics_run() {
        let fake = Fake::new("ok");
        fake.installed("0.4.0");
        let dir = fake
            .dir
            .path()
            .join(format!("humanize-{}", unsafe { libc::getuid() }));
        fs::create_dir_all(&dir).unwrap();
        let pid = std::process::id();
        fs::write(dir.join("daemon.json"), format!(r#"{{"pid": {pid}}}"#)).unwrap();
        let (chosen, told) = fake.choose("0.5.0", How::Usual);
        assert_eq!(chosen, Ok(Chosen::Held(fake.hmz(), "0.4.0".into())));
        assert!(told.is_empty());
        assert_eq!(fake.argv(), "");

        // Asked to, it does: an update.
        let (chosen, told) = fake.choose("0.5.0", How::Now);
        assert_eq!(chosen, Ok(Chosen::Ready(fake.hmz())));
        assert!(told.iter().all(|p| p.updating));
        assert_eq!(version_of(&fake.hmz(), &fake.env).as_deref(), Some("0.5.0"));
    }

    #[cfg(unix)]
    #[test]
    fn says_why_it_did_not_install_and_whether_to_keep_the_old() {
        let fake = Fake::new("offline");
        let (chosen, _) = fake.choose("0.5.0", How::Usual);
        let failed = chosen.unwrap_err();
        assert!(!failed.updating && !failed.keep);
        assert!(failed.said.contains("Failed to fetch"), "{}", failed.said);

        // One there that takes `web --attached` can be kept, and is, when asked.
        let fake = Fake::new("offline");
        fake.installed("0.4.0");
        let failed = fake.choose("0.5.0", How::Usual).0.unwrap_err();
        assert!(failed.updating && !failed.keep);
        fs::write(
            fake.hmz(),
            "#!/bin/sh\n[ \"$1\" = --version ] && echo 'hmz 0.4.0'\necho 'usage: hmz web [--attached]'\n",
        )
        .unwrap();
        let failed = fake.choose("0.5.0", How::Usual).0.unwrap_err();
        assert!(failed.updating && failed.keep);
        assert_eq!(
            fake.choose("0.5.0", How::Keep).0,
            Ok(Chosen::Ready(fake.hmz()))
        );

        let failed = Fake::new("wrong")
            .choose("0.5.0", How::Usual)
            .0
            .unwrap_err();
        assert!(failed.said.contains("9.9.9"), "{}", failed.said);
    }

    #[cfg(unix)]
    #[test]
    fn quitting_while_it_installs_stops_uv_and_starts_nothing_after() {
        if child::tests::apart(
            "install::tests::quitting_while_it_installs_stops_uv_and_starts_nothing_after",
        ) {
            return;
        }
        let fake = Fake::new("slow");
        let pid = fake.dir.path().join("tools/pid");
        let installing = std::thread::spawn(move || (fake.choose("0.5.0", How::Usual).0, fake));
        let pid = child::tests::written(&pid);
        let began = std::time::Instant::now();
        child::quit();
        let (chosen, fake) = installing.join().unwrap();
        assert!(began.elapsed() < child::STOPPING);
        assert!(chosen.is_err());
        assert!(child::tests::gone(pid));
        assert_eq!(fake.argv().lines().count(), 1);
        assert!(!fake.hmz().exists());
    }

    #[cfg(unix)]
    #[test]
    fn installs_nothing_for_a_development_build_or_a_named_hmz() {
        let fake = Fake::new("ok");
        assert_eq!(fake.choose("0.0.0", How::Usual).0, Ok(Chosen::Missing));
        fake.installed("0.4.0");
        let mut named = Fake::new("ok");
        named.env.insert(server::OVERRIDE.into(), fake.hmz().into());
        assert_eq!(
            named.choose("0.5.0", How::Usual).0,
            Ok(Chosen::Ready(fake.hmz()))
        );
        assert_eq!(named.argv(), "");
        assert_eq!(fake.argv(), "");
    }
}
