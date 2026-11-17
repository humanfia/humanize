//! On Windows, the `hmz` the app runs in WSL (Section 3.4 of [DESKTOP]): the release's own, put
//! and kept there by `uv tool` -- WSL's uv, or one the app downloads into it -- just as a
//! terminal user installs it. Never while an `hmz` of another version holds running epics: an
//! install takes its files from under them.

use std::ffi::OsStr;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;

use flate2::read::GzDecoder;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::child;
use crate::hmz;
use crate::pipes::pep440;
use crate::shell_env::{self, Env};

/// The uv the app downloads where WSL has none, for each architecture, and its archive's sha256
/// as astral-sh/uv published it.
const UV: &str = "0.12.24";
const UV_TARGET: &str = "unknown-linux-gnu";
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
/// the app's data directory is out of WSL's reach.
const OWN_UV: &str = ".local/bin";

/// Runs `$@`, uv, in WSL so that `wsl.exe` killed, as quitting does, stops it as on a Mac. The
/// hangup goes to this shell alone, which interrupts uv as Ctrl+C would, and kills it where it
/// has not stopped in time. uv runs as a job of its own, so that an interrupt is not ignored, and
/// says what it says into a file, followed from there, which no hangup closes.
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

/// What an install that failed says first where there is no WSL to install in: the splash shows
/// it as such.
const NO_WSL: &str = "WSL missing";

/// How long WSL may take to start, its virtual machine with it.
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

/// What is being done, as the splash shows it.
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
/// kept instead -- one that can serve the app.
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
    /// build (Section 3.4.12 and Section 3.4.13 of [DESKTOP]).
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
    version: &str,
    how: How,
    tell: &dyn Fn(Progress),
) -> Result<Chosen, Failed> {
    wsl().map_err(|why| Failed {
        updating: false,
        said: format!("{NO_WSL}: {why}"),
        keep: false,
    })?;
    let named = env
        .get(OsStr::new(hmz::OVERRIDE))
        .is_some_and(|named| !named.is_empty());
    let Some(pinned) = pep440(version).filter(|_| !named) else {
        return Ok(hmz::find(env).map_or(Chosen::Missing, Chosen::Ready));
    };
    let failed = |said| Failed {
        updating: false,
        said,
        keep: false,
    };
    let (uv, bin) = match uvs(env).iter().find_map(|uv| answers(uv, env)) {
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
            let own = joined(&shell_env::home(env), OWN_UV);
            let uv = download(env, &own, &getting).map_err(failed)?;
            answers(&uv, env).ok_or_else(|| failed(format!("{} did not answer", uv.display())))?
        }
    };
    let hmz = joined(&bin, "hmz");
    if how == How::Keep {
        return Ok(Chosen::Ready(hmz));
    }
    let updating = hmz::runnable(&hmz);
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
                        keep: serves(&hmz, env),
                    })
                }
            }
        }
    }
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

/// Where to look for uv in WSL, each place once: `PATH`, then the places its installers put it
/// (Section 3.4.6 of [DESKTOP]).
pub fn uvs(env: &Env) -> Vec<PathBuf> {
    let home = shell_env::home(env);
    let path = env.get(OsStr::new("PATH")).map(|path| split(path));
    let dirs = path.into_iter().flatten().filter(|dir| dir.has_root());
    let mut uvs: Vec<PathBuf> = Vec::new();
    for dir in dirs.chain([joined(&home, ".local/bin"), joined(&home, ".cargo/bin")]) {
        let uv = joined(&dir, "uv");
        if !uvs.contains(&uv) {
            uvs.push(uv);
        }
    }
    uvs
}

/// The directories in WSL's `PATH`, split as Linux splits it.
fn split(path: &OsStr) -> Vec<PathBuf> {
    path.to_string_lossy()
        .split(':')
        .map(PathBuf::from)
        .collect()
}

/// `name` in `dir`, a path in WSL, joined as Linux joins it.
fn joined(dir: &Path, name: &str) -> PathBuf {
    format!("{}/{name}", dir.to_string_lossy().trim_end_matches('/')).into()
}

/// A program run in WSL, in the login shell's environment there alone.
fn command(program: &Path, env: &Env) -> Command {
    crate::wsl::command(program, Some(env))
}

/// uv, as it is run to install: interrupted, and killed, as quitting stops what `wsl.exe` runs.
fn installing(uv: &Path, env: &Env) -> Command {
    let mut command = crate::wsl::command("/bin/sh", Some(env));
    command.args(["-c", INTERRUPTIBLE, "sh"]).arg(uv);
    command
}

/// Whether there is a WSL to install in: `wsl.exe`, and a distribution it starts.
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
    if !hmz::runnable(uv) {
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

/// Whether an `hmz` can serve the app: it takes `daemon connect --stdio`, which the page's pipe
/// to Local runs.
pub fn serves(path: &Path, env: &Env) -> bool {
    hmz::runnable(path)
        && asked(path, ["daemon", "connect", "--help"], env).is_some_and(|h| h.contains("--stdio"))
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

/// Whether WSL's daemon is running: it holds a workspace's epics, or is about to let go. What a
/// daemon writes beside its socket -- `daemon.json` in `humanize-<uid>` in the temporary
/// directory -- names its process, looked for in WSL (Section 4.7.1 of [DESKTOP]).
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
/// each line uv says; then checks the `hmz` there is that version (Section 4.6.1 of [DESKTOP]).
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
    // `wsl.exe` starts it in WSL's home.
    let mut command = installing(uv, env);
    command
        .args(["tool", "install", "--force"])
        // A Python hmz runs on, downloaded where there is none: uv would take the first found.
        .args(["--python", PYTHON])
        // Asked of the index again: a release this new may be missing from what uv has cached.
        .args(["--refresh-package", "hmz"])
        .arg(&wanted)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
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

/// The uv of `UV` for WSL's architecture from its GitHub release into `dir`, checked against the
/// sum pinned here.
fn download(env: &Env, dir: &Path, tell: &dyn Fn(&str)) -> Result<PathBuf, String> {
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
        // What the system trusts, a company's own authority in the store included.
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

/// The sha256 of `bytes`, in lowercase hex.
fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// The `uv` in a release archive, once its sha256 is the one expected.
pub fn unpacked(archive: &[u8], sha256: &str) -> Result<Vec<u8>, String> {
    let sum = sha256_hex(archive);
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

/// Writes what it reads to `uv` in `$1` in WSL: beside it first, and moved into place once its
/// sha256 is `$2`, so it is never there half written -- `wsl.exe` killed ends what it reads.
const WRITE: &str = r#"mkdir -p "$1" && new="$1/.uv.$$.new" || exit
trap 'rm -f "$new"; exit 1' HUP INT TERM
cat > "$new" && echo "$2  $new" | sha256sum -c --status && chmod 755 "$new" &&
mv -f "$new" "$1/uv" || { rm -f "$new"; exit 1; }"#;

/// The `uv` in a release archive, once its sha256 is the one expected, written into `dir` in
/// WSL (Section 4.6.6 of [DESKTOP]).
pub fn unpack(archive: &[u8], sha256: &str, dir: &Path) -> Result<PathBuf, String> {
    let unpacked = unpacked(archive, sha256)?;
    let mut command = crate::wsl::command("/bin/sh", None);
    command
        .args(["-c", WRITE, "sh"])
        .arg(dir)
        .arg(sha256_hex(&unpacked))
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

    #[test]
    fn looks_for_uv_along_wsls_path_then_where_installers_put_it() {
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b/:/home/u/.local/bin".into()),
            ("HOME".into(), "/home/u".into()),
        ]);
        let found: Vec<PathBuf> = uvs(&env);
        let expected: Vec<PathBuf> = [
            "/a/uv",
            "/b/uv",
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
        let sum = sha256_hex(&good);
        assert_eq!(unpacked(&good, &sum).unwrap(), b"#!/bin/sh\n");
        let tampered = archive("uv-x86_64-unknown-linux-gnu/uv", b"#!/bin/sh\nevil\n");
        let refused = unpacked(&tampered, &sum).unwrap_err();
        assert!(refused.contains("sha256"), "{refused}");
        let empty = archive("uv-x86_64-unknown-linux-gnu/uvx", b"");
        let sum = sha256_hex(&empty);
        assert!(unpacked(&empty, &sum).is_err());
    }

    #[test]
    fn pins_a_sum_for_each_architecture() {
        assert_eq!(UV_SHA256.map(|(arch, _)| arch), ["aarch64", "x86_64"]);
        for (_, sum) in UV_SHA256 {
            assert_eq!(sum.len(), 64);
            assert!(sum.chars().all(|c| c.is_ascii_hexdigit()));
        }
    }

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
}
