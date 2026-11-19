//! Processes of a pipe: those whose standard input and output are its carrier --
//! `hmz daemon connect --stdio` on this Mac, in WSL or over `ssh` (Section 3.4.2 to Section
//! 3.4.4 of [WIRE]) -- and those asked something on its way, each kept so that closing the pipe
//! or quitting the app stops it as `child.rs` stops every child.

use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::runtime::Handle;

use super::Stream;
use super::route::Ssh;
use crate::child::{self, Child};
use crate::lock;

/// The processes a pipe started; none more once it is closed.
#[derive(Default)]
pub struct Kids(Mutex<Option<Vec<Arc<Child>>>>);

impl Kids {
    pub fn new() -> Arc<Kids> {
        Arc::new(Kids(Mutex::new(Some(Vec::new()))))
    }

    /// Starts a command for the pipe.
    pub fn spawn(&self, command: &mut Command) -> Result<Arc<Child>, String> {
        let mut kids = lock(&self.0);
        let Some(kids) = kids.as_mut() else {
            return Err("the pipe is closed".into());
        };
        let program = command.get_program().to_string_lossy().into_owned();
        let kid = Arc::new(
            child::spawn(command).map_err(|why| format!("{program} could not be run: {why}"))?,
        );
        kids.push(kid.clone());
        Ok(kid)
    }

    /// Stops every process of the pipe, interrupting each and killing what does not stop.
    pub fn end(&self) {
        let kids = lock(&self.0).take().unwrap_or_default();
        for kid in kids {
            child::ended(&kid);
        }
    }
}

/// What a pipe's processes said last on their standard error.
pub type Said = Arc<Mutex<String>>;

/// What `hmz daemon connect --stdio` writes before the daemon's first byte, and what the
/// carrier begins after (Section 3.4.11 of [WIRE]).
const SYNC: &[u8] = b"hmz-stdio/1\n";

/// How many bytes may come before [`SYNC`] hold it.
const SYNCING: usize = 1 << 16;

/// Reads `out` up to and including the first [`SYNC`] -- what a shell printed before `hmz`
/// ran -- and answers what came after it in the same reads; None where `out` ended first.
fn synced(out: &mut impl Read) -> Result<Option<Vec<u8>>, String> {
    let mut seen = Vec::new();
    let mut chunk = vec![0; 1 << 14];
    loop {
        let n = match out.read(&mut chunk) {
            Ok(0) | Err(_) => return Ok(None),
            Ok(n) => n,
        };
        seen.extend_from_slice(&chunk[..n]);
        let within = &seen[..seen.len().min(SYNCING)];
        if let Some(at) = within.windows(SYNC.len()).position(|line| line == SYNC) {
            return Ok(Some(seen.split_off(at + SYNC.len())));
        }
        if seen.len() >= SYNCING {
            return Err(format!(
                "No hmz-stdio/1 line came within the first {SYNCING} bytes."
            ));
        }
    }
}

/// The carrier a started process's standard input and output are, from after the line
/// [`SYNC`], its standard error logged line by line and its last line kept. On Windows, the
/// first line a `wsl.exe` says there is the pid in WSL of what it runs.
pub fn carried(kid: &Arc<Child>, said: &Said, wsl: bool) -> Result<Stream, String> {
    let (Some(mut stdin), Some(mut stdout), Some(stderr)) =
        (kid.take_stdin(), kid.take_stdout(), kid.take_stderr())
    else {
        return Err("the process could not be read".into());
    };
    let failed = said.clone();
    let said = said.clone();
    #[cfg(windows)]
    let pid = kid.id();
    let (ended, errors) = mpsc::channel::<()>();
    thread::spawn(move || {
        let _ended = ended;
        let mut first = wsl;
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            if std::mem::take(&mut first)
                && let Ok(inside) = line.trim().parse::<u32>()
            {
                #[cfg(windows)]
                child::inside(pid, inside);
                #[cfg(not(windows))]
                let _ = inside;
                continue;
            }
            log::info!("pipe: {line}");
            if !line.trim().is_empty() {
                *lock(&said) = line.trim().to_owned();
            }
        }
    });
    let (ours, theirs) = tokio::io::duplex(1 << 16);
    let (mut from, mut to) = tokio::io::split(theirs);
    let handle = Handle::current();
    let reading = handle.clone();
    thread::spawn(move || {
        let mut chunk = vec![0; 1 << 14];
        let first = synced(&mut stdout);
        if let Ok(Some(first)) = &first
            && reading.block_on(to.write_all(first)).is_ok()
        {
            while let Ok(n @ 1..) = stdout.read(&mut chunk) {
                if reading.block_on(to.write_all(&chunk[..n])).is_err() {
                    break;
                }
            }
        }
        // Ended once what it said last on its standard error is kept -- unless something it
        // left behind holds its standard error open.
        let _ = errors.recv_timeout(Duration::from_secs(1));
        if let Err(why) = first {
            *lock(&failed) = why;
        }
        let _ = reading.block_on(to.shutdown());
    });
    thread::spawn(move || {
        let mut chunk = vec![0; 1 << 14];
        while let Ok(n @ 1..) = handle.block_on(from.read(&mut chunk)) {
            if stdin
                .write_all(&chunk[..n])
                .and_then(|()| stdin.flush())
                .is_err()
            {
                break;
            }
        }
        // Its end of input: `hmz daemon connect --stdio` exits on it.
    });
    Ok(Box::new(ours))
}

/// `command` with its standard streams piped, as a carrier's process is started.
fn piped(command: &mut Command) -> &mut Command {
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
}

/// What `"$SHELL" -lc` runs, through `sh` whatever that shell is, for `stdio:local`: the `hmz`
/// on the `PATH` it gives, `$HOME/.local/bin` added where it lacks it, or the one
/// `HUMANIZE_HMZ` names (Section 3.4.12 of [DESKTOP]), connecting.
#[cfg(unix)]
const LOCALLY: &str = r#"case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$PATH:$HOME/.local/bin"; export PATH ;; esac; exec "${HUMANIZE_HMZ:-hmz}" daemon connect --stdio"#;

/// `"$SHELL" -lc` running [`LOCALLY`], `/bin/sh` standing for `$SHELL` where it is not set, in
/// the environment given, from `home`.
#[cfg(unix)]
pub fn local(env: &crate::shell_env::Env) -> Command {
    let shell = env
        .get(std::ffi::OsStr::new("SHELL"))
        .filter(|shell| !shell.is_empty())
        .cloned()
        .unwrap_or_else(|| "/bin/sh".into());
    let mut command = Command::new(shell);
    command
        .arg("-lc")
        .arg(format!("exec /bin/sh -c {}", quoted(LOCALLY)))
        .env_clear()
        .envs(env)
        .current_dir(crate::shell_env::home(env));
    piped(&mut command);
    command
}

/// What WSL runs for `stdio:wsl`: says its pid on its standard error, then becomes, through a
/// login shell, the `hmz` `HUMANIZE_HMZ` names, or else the one it finds with `$HOME/.local/bin`
/// put in front of its `PATH`, connecting.
#[cfg(any(windows, test))]
const IN_WSL: &str = r#"echo $$ >&2; exec "${SHELL:-/bin/sh}" -lc "exec /bin/sh -c 'PATH=\"\$HOME/.local/bin:\$PATH\"; export PATH; exec \"\${HUMANIZE_HMZ:-hmz}\" daemon connect --stdio'""#;

/// `wsl.exe [-d <distro>] --exec … hmz daemon connect --stdio`, with `hmz`, a path in WSL,
/// where one is given.
#[cfg(windows)]
pub fn wsl(distro: Option<&str>, hmz: Option<&str>) -> Command {
    let mut command = crate::wsl::command_in(distro, "/usr/bin/env", None);
    if let Some(hmz) = hmz {
        command.arg(format!("{}={hmz}", crate::hmz::OVERRIDE));
    }
    command.args(["/bin/sh", "-c", IN_WSL]);
    piped(&mut command);
    command
}

/// What every command run over ssh is run with: where `uv tool` and astral's installer put
/// what they install, which a shell that is not a login one may not have on its `PATH`.
const THERE: &str = r#"export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"; "#;

/// Asked of the host before anything is started there: the version of its `hmz`, and whether
/// its daemon is running, as `hmz` itself asks it.
const PROBE: &str = r#"echo "hmz: $(hmz --version 2>/dev/null | sed -n 's/^hmz //p' | tail -n 1)"
daemon=none
for under in "$TMPDIR" "$TEMP" "$TMP" "$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null)" \
    /tmp /var/tmp; do
  [ -n "$under" ] || continue
  record="${under%/}/humanize-$(id -u)/daemon.json"
  [ -e "$record" ] || continue
  if [ ! -r "$record" ]; then daemon=unknown; continue; fi
  pid=$(sed -n 's/.*"pid": *\([0-9][0-9]*\).*/\1/p' "$record" | head -n 1)
  if [ -z "$pid" ]; then daemon=unknown
  elif kill -0 "$pid" 2>/dev/null || ps -p "$pid" >/dev/null 2>&1; then
    daemon=running; break
  fi
done
echo "daemon: $daemon"
"#;

/// The uv fetched where the host has none: the one `hmz` itself pins.
const UV: &str = "0.12.24";

/// Installs `hmz` of a version, `{version}`, fetching uv first where there is none.
fn installing(version: &str) -> String {
    format!(
        "export UV_NO_MODIFY_PATH=1; \
         if ! command -v uv >/dev/null 2>&1; then \
         echo 'Getting uv {UV}'; \
         if command -v curl >/dev/null 2>&1; \
         then curl -LsSf https://astral.sh/uv/{UV}/install.sh | sh; \
         else wget -qO- https://astral.sh/uv/{UV}/install.sh | sh; fi; \
         command -v uv >/dev/null 2>&1 || exit 1; fi; \
         exec uv tool install --force --python '>=3.12' 'hmz=={version}'"
    )
}

/// Connects, for as long as the ssh holding its standard input lives.
const CONNECT: &str = "exec hmz daemon connect --stdio";

/// How long asking the host may take.
const PROBING: Duration = Duration::from_secs(30);

/// How long installing `hmz` there may take.
const INSTALLING: Duration = Duration::from_secs(900);

/// `ssh` reaching the route's host, asking nothing of anybody, running `script` there with
/// `sh`. On Windows it is WSL's `ssh`, run through `wsl.exe`: the hosts the page offers and
/// the identity files it imports are those of Local's ssh config, which is WSL's (Section
/// 3.13.5 of [WEB] and Section 3.5.6 of [DESKTOP]), and Windows' own `ssh` reads another.
/// Killing that `wsl.exe` hangs up the `ssh` it runs, which ends on it.
pub fn ssh(route: &Ssh, script: &str) -> Command {
    #[cfg(not(windows))]
    let mut command = Command::new("ssh");
    #[cfg(windows)]
    let mut command = crate::wsl::command("ssh", None);
    // First, so that no option given after takes it back: ssh keeps the first of each.
    command.args(["-T", "-o", "BatchMode=yes"]);
    if let Some(port) = route.port {
        command.arg("-p").arg(port.to_string());
    }
    if let Some(identity) = &route.identity {
        command.arg("-i").arg(identity);
    }
    if let Some(jump) = &route.jump {
        command.arg("-J").arg(jump);
    }
    for option in &route.options {
        command.arg("-o").arg(option);
    }
    command.args(["-o", "ConnectTimeout=20", "--"]);
    command.arg(match &route.user {
        Some(user) => format!("{user}@{}", route.host),
        None => route.host.clone(),
    });
    command.arg(format!("sh -c {}", quoted(&format!("{THERE}{script}"))));
    command
}

/// `text` in single quotes, as a shell reads it back.
fn quoted(text: &str) -> String {
    format!("'{}'", text.replace('\'', r"'\''"))
}

/// Runs a command to its end, telling each line it says on its standard output or error --
/// `ssh`'s own, and what the host's says -- within `limit`, failing with `late` beyond it.
fn ran(
    kids: &Kids,
    command: &mut Command,
    limit: Duration,
    late: &str,
    each: &dyn Fn(&str),
) -> Result<(bool, Vec<String>), String> {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let kid = kids.spawn(command)?;
    let (Some(stdout), Some(stderr)) = (kid.take_stdout(), kid.take_stderr()) else {
        return Err("the process could not be read".into());
    };
    let (heard, hear) = mpsc::channel();
    let heard_too = heard.clone();
    thread::spawn(move || lines(stdout, &heard));
    thread::spawn(move || lines(stderr, &heard_too));
    let began = Instant::now();
    let mut lines = Vec::new();
    loop {
        let left = limit.saturating_sub(began.elapsed());
        match hear.recv_timeout(left) {
            Ok(line) => {
                each(&line);
                lines.push(line);
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                child::ended(&kid);
                return Err(late.to_owned());
            }
        }
    }
    let ok = kid.wait().is_ok_and(|status| status.success());
    Ok((ok, lines))
}

/// Each line `out` says, sent on until it ends.
fn lines(out: impl Read, heard: &mpsc::Sender<String>) {
    for line in BufReader::new(out).lines().map_while(Result::ok) {
        if heard.send(line).is_err() {
            break;
        }
    }
}

/// What the probe found: the version of `hmz` there, empty where none, and whether its daemon
/// is `none`, `running` or `unknown`; `name` is the route, said where the host is silent
/// beyond [`PROBING`] (Section 3.4.9 of [WIRE]).
fn probed(kids: &Kids, route: &Ssh, name: &str) -> Result<(String, String), String> {
    let late = format!("{name} did not open within {} seconds.", PROBING.as_secs());
    let (ok, lines) = ran(kids, &mut ssh(route, PROBE), PROBING, &late, &|_| {})?;
    let field = |key: &str| {
        lines.iter().find_map(|line| {
            let (k, v) = line.split_once(':')?;
            (k == key).then(|| v.trim().to_owned())
        })
    };
    match (ok, field("hmz"), field("daemon")) {
        (true, Some(hmz), Some(daemon)) => Ok((hmz, daemon)),
        _ => Err(last(&lines, &format!("{} did not answer.", route.host))),
    }
}

/// The last line said that is not blank, or `otherwise`.
fn last(lines: &[String], otherwise: &str) -> String {
    lines
        .iter()
        .rev()
        .map(|line| line.trim())
        .find(|line| !line.is_empty())
        .unwrap_or(otherwise)
        .to_owned()
}

/// Finds the `hmz` on the route's host and installs the app's own there where it must
/// (Section 3.8.3 of [DAEMON]), then starts `hmz daemon connect --stdio` there. `wanted` is
/// the app's version as PyPI has it, None for a development build; `name` is the route as
/// written; `say` is told the state and what was said last.
pub fn reach_ssh(
    kids: &Kids,
    route: &Ssh,
    name: &str,
    wanted: Option<&str>,
    say: &dyn Fn(&'static str, &str),
) -> Result<Arc<Child>, String> {
    let host = &route.host;
    say("connecting", &format!("ssh {host}"));
    let (there, daemon) = probed(kids, route, name)?;
    match wanted.filter(|&wanted| wanted != there) {
        // A development build installs nothing, and uses what is there.
        None if there.is_empty() => return Err(format!("hmz is not installed on {host}.")),
        None => {}
        Some(wanted) if !there.is_empty() && daemon != "none" => {
            let why = if daemon == "running" {
                format!("hmz {there} there holds running epics; hmz {wanted} waits")
            } else {
                format!("Whether hmz {there} there runs epics is unknown; not replaced")
            };
            say("connecting", &why);
        }
        Some(wanted) => {
            say("installing", &format!("hmz {wanted}"));
            let tell = |line: &str| {
                if !line.trim().is_empty() {
                    say("installing", line.trim());
                }
            };
            let script = installing(wanted);
            let late = format!(
                "hmz {wanted} was not installed within {} seconds.",
                INSTALLING.as_secs()
            );
            let (ok, lines) = ran(kids, &mut ssh(route, &script), INSTALLING, &late, &tell)?;
            if !ok {
                return Err(last(
                    &lines,
                    &format!("hmz {wanted} could not be installed."),
                ));
            }
            let (there, _) = probed(kids, route, name)?;
            if there != wanted {
                return Err(format!(
                    "hmz {wanted} was installed, and hmz {there} answers."
                ));
            }
        }
    }
    let mut connect = ssh(route, CONNECT);
    kids.spawn(piped(&mut connect))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(command: &Command) -> Vec<String> {
        command
            .get_args()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect()
    }

    /// On Windows, what WSL's `ssh` is given, once `wsl.exe` is seen to run it from the home
    /// of the default distribution; elsewhere, `args` as they are.
    fn in_wsl(args: Vec<String>) -> Vec<String> {
        #[cfg(windows)]
        let args = {
            assert_eq!(args[..4], ["--cd", "~", "--exec", "ssh"]);
            args[4..].to_vec()
        };
        args
    }

    /// The hosts the page offers are those of WSL's ssh config (`runtimes.hosts` of Local),
    /// so it is WSL's `ssh` that reaches them, not Windows' own.
    #[cfg(windows)]
    #[test]
    fn runs_the_ssh_of_wsl_on_windows() {
        let route = Ssh {
            host: "box".into(),
            identity: Some("/home/me/.ssh/id".into()),
            ..Ssh::default()
        };
        let command = ssh(&route, CONNECT);
        assert_eq!(command.get_program(), "wsl.exe");
        let args = args(&command);
        assert_eq!(args[..4], ["--cd", "~", "--exec", "ssh"]);
        // The identity file is a path of WSL, given as it is written.
        assert!(
            args.windows(2)
                .any(|pair| pair == ["-i", "/home/me/.ssh/id"])
        );
    }

    #[test]
    fn runs_ssh_in_batch_mode_with_what_the_route_says() {
        let route = Ssh {
            user: Some("me".into()),
            host: "box".into(),
            port: Some(2222),
            identity: Some("~/.ssh/id".into()),
            jump: Some("gw".into()),
            options: vec!["BatchMode=no".into(), "Compression=yes".into()],
        };
        let command = ssh(&route, CONNECT);
        #[cfg(not(windows))]
        assert_eq!(command.get_program(), "ssh");
        let args = |command: &Command| in_wsl(args(command));
        let mut want: Vec<String> = [
            "-T",
            "-o",
            "BatchMode=yes",
            "-p",
            "2222",
            "-i",
            "~/.ssh/id",
            "-J",
            "gw",
            "-o",
            "BatchMode=no",
            "-o",
            "Compression=yes",
            "-o",
            "ConnectTimeout=20",
            "--",
            "me@box",
        ]
        .map(String::from)
        .to_vec();
        want.push(format!("sh -c '{THERE}{CONNECT}'"));
        assert_eq!(args(&command), want);
        let bare = ssh(
            &Ssh {
                host: "-oProxyCommand=x".into(),
                ..Ssh::default()
            },
            "it's",
        );
        let bare = args(&bare);
        // A host is never read as an option.
        assert_eq!(
            bare[bare.len() - 3..bare.len() - 1],
            ["--", "-oProxyCommand=x"]
        );
        assert!(bare.last().unwrap().ends_with(r"it'\''s'"));
    }

    #[cfg(unix)]
    #[test]
    fn the_scripts_say_what_they_mean_to_sh() {
        // Each read back by sh as it was written.
        for script in [PROBE, THERE, &installing("1.2.3"), IN_WSL, LOCALLY] {
            let out = Command::new("/bin/sh")
                .args(["-c", &format!("printf %s {}", quoted(script))])
                .output()
                .unwrap();
            assert_eq!(String::from_utf8(out.stdout).unwrap(), script);
            let parsed = Command::new("/bin/sh")
                .args(["-n", "-c", script])
                .status()
                .unwrap();
            assert!(parsed.success(), "{script}");
        }
    }

    /// A home whose `~/.local/bin` holds an `hmz`, another `hmz` elsewhere, and a login shell
    /// that reads no profile, which would say what this machine's says: each `hmz` says which
    /// it is and what it was asked.
    #[cfg(unix)]
    fn two_hmzs() -> (tempfile::TempDir, std::path::PathBuf, std::path::PathBuf) {
        let home = tempfile::tempdir().unwrap();
        let script = |path: &std::path::Path, text: &str| {
            use std::os::unix::fs::PermissionsExt;
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, text).unwrap();
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
        };
        let bin = home.path().join(".local/bin");
        script(&bin.join("hmz"), "#!/bin/sh\necho \"local hmz $*\"\n");
        let elsewhere = home.path().join("elsewhere");
        script(&elsewhere.join("hmz"), "#!/bin/sh\necho \"path hmz $*\"\n");
        let shell = home.path().join("shell");
        script(
            &shell,
            "#!/bin/sh\n[ \"$1\" = -lc ] && exec /bin/sh -c \"$2\"\n",
        );
        (home, elsewhere, shell)
    }

    #[cfg(unix)]
    #[test]
    fn wsl_and_ssh_put_the_local_bin_before_path() {
        let (home, elsewhere, shell) = two_hmzs();
        let path = format!("{}:/usr/bin:/bin", elsewhere.display());
        // What WSL's login shell is handed, run by sh here.
        let out = Command::new("/bin/sh")
            .args(["-c", IN_WSL])
            .env_clear()
            .env("HOME", home.path())
            .env("PATH", &path)
            .env("SHELL", &shell)
            .output()
            .unwrap();
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            "local hmz daemon connect --stdio\n"
        );
        let pid = String::from_utf8(out.stderr).unwrap();
        assert!(pid.trim().parse::<u32>().is_ok(), "{pid}");
        // The hmz the app chose, where it names one.
        let out = Command::new("/bin/sh")
            .args(["-c", IN_WSL])
            .env_clear()
            .env("HOME", home.path())
            .env("PATH", "/usr/bin:/bin")
            .env("SHELL", &shell)
            .env("HUMANIZE_HMZ", elsewhere.join("hmz"))
            .output()
            .unwrap();
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            "path hmz daemon connect --stdio\n"
        );
        // What ssh has the host's shell run, run by sh here.
        let out = Command::new("/bin/sh")
            .args(["-c", &format!("{THERE}{CONNECT}")])
            .env_clear()
            .env("HOME", home.path())
            .env("PATH", &path)
            .output()
            .unwrap();
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            "local hmz daemon connect --stdio\n"
        );
    }

    #[cfg(unix)]
    #[test]
    fn runs_local_through_the_login_shell_adding_the_local_bin_where_it_lacks_it() {
        let (home, elsewhere, shell) = two_hmzs();
        let env = |path: &str, shell: Option<&std::path::Path>| {
            let mut env = crate::shell_env::Env::new();
            env.insert("HOME".into(), home.path().into());
            env.insert("PATH".into(), path.into());
            if let Some(shell) = shell {
                env.insert("SHELL".into(), shell.into());
            }
            env
        };
        let said = |path: &str| {
            let out = local(&env(path, Some(&shell))).output().unwrap();
            String::from_utf8(out.stdout).unwrap()
        };
        // The login shell's PATH first; ~/.local/bin after it, where it lacks it.
        let path = format!("{}:/usr/bin:/bin", elsewhere.display());
        assert_eq!(said(&path), "path hmz daemon connect --stdio\n");
        assert_eq!(said("/usr/bin:/bin"), "local hmz daemon connect --stdio\n");
        let command = local(&env("/usr/bin:/bin", Some(&shell)));
        assert_eq!(command.get_program(), shell.as_os_str());
        assert_eq!(
            args(&command),
            [
                "-lc".to_owned(),
                format!("exec /bin/sh -c {}", quoted(LOCALLY))
            ]
        );
        assert_eq!(command.get_current_dir(), Some(home.path()));
        // The hmz HUMANIZE_HMZ names, where it is set.
        let mut named = env("/usr/bin:/bin", Some(&shell));
        named.insert("HUMANIZE_HMZ".into(), elsewhere.join("hmz").into());
        let out = local(&named).output().unwrap();
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            "path hmz daemon connect --stdio\n"
        );
        // /bin/sh where $SHELL is not set.
        assert_eq!(local(&env("/usr/bin:/bin", None)).get_program(), "/bin/sh");
    }

    #[cfg(unix)]
    #[tokio::test(flavor = "multi_thread")]
    async fn carries_bytes_through_a_process_both_ways() {
        let kids = Kids::new();
        // What a shell printed first, then the sync line, then the daemon's bytes.
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "echo Welcome; echo hmz-stdio/1; exec cat"]);
        let kid = kids.spawn(piped(&mut command)).unwrap();
        let said = Said::default();
        let mut stream = carried(&kid, &said, false).unwrap();
        stream.write_all(b"hello, daemon").await.unwrap();
        let mut back = [0u8; 13];
        stream.read_exact(&mut back).await.unwrap();
        assert_eq!(&back, b"hello, daemon");
        // Closing the pipe stops it, and the carrier ends.
        tokio::task::spawn_blocking(move || kids.end())
            .await
            .unwrap();
        assert!(kid.try_wait().unwrap().is_some());
        assert!(kids_refuse_more());
        let mut rest = Vec::new();
        stream.read_to_end(&mut rest).await.unwrap();
        assert!(rest.is_empty());
    }

    #[test]
    fn a_carrier_begins_after_the_first_sync_line_within_64_kib() {
        let read = |said: &[u8]| synced(&mut std::io::Cursor::new(said.to_vec()));
        assert_eq!(
            read(b"Welcome\nhmz-stdio/1\nframes hmz-stdio/1\n"),
            Ok(Some(b"frames hmz-stdio/1\n".to_vec()))
        );
        // The line split between two reads.
        let mut split = vec![b'x'; (1 << 14) - 4];
        split.extend_from_slice(SYNC);
        split.extend_from_slice(b"frames");
        assert_eq!(read(&split), Ok(Some(b"frames".to_vec())));
        let mut late = vec![b'x'; SYNCING - SYNC.len()];
        late.extend_from_slice(SYNC);
        late.extend_from_slice(b"frames");
        // Its last byte the 65536th: what follows is read after.
        assert_eq!(read(&late), Ok(Some(Vec::new())));
        late.insert(0, b'x');
        assert_eq!(
            read(&late),
            Err("No hmz-stdio/1 line came within the first 65536 bytes.".into())
        );
        assert_eq!(read(b"hmz: not found\n"), Ok(None));
    }

    #[cfg(unix)]
    #[tokio::test(flavor = "multi_thread")]
    async fn ends_a_carrier_without_the_sync_line_saying_so() {
        let kids = Kids::new();
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "head -c 70000 /dev/zero; echo hmz-stdio/1; exec cat"]);
        let kid = kids.spawn(piped(&mut command)).unwrap();
        let said = Said::default();
        let mut stream = carried(&kid, &said, false).unwrap();
        let mut rest = Vec::new();
        stream.read_to_end(&mut rest).await.unwrap();
        assert!(rest.is_empty());
        assert_eq!(
            *lock(&said),
            "No hmz-stdio/1 line came within the first 65536 bytes."
        );
        tokio::task::spawn_blocking(move || kids.end())
            .await
            .unwrap();
    }

    #[cfg(unix)]
    fn kids_refuse_more() -> bool {
        let kids = Kids::new();
        kids.end();
        kids.spawn(&mut Command::new("/bin/echo")).is_err()
    }

    #[cfg(unix)]
    #[tokio::test(flavor = "multi_thread")]
    async fn keeps_the_last_line_said_on_standard_error() {
        let kids = Kids::new();
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "echo one >&2; echo 'two words' >&2; echo >&2"]);
        let kid = kids.spawn(piped(&mut command)).unwrap();
        let said = Said::default();
        let mut stream = carried(&kid, &said, false).unwrap();
        let mut rest = Vec::new();
        stream.read_to_end(&mut rest).await.unwrap();
        let _ = kid.wait();
        // Its standard error is read apart from its output.
        for _ in 0..100 {
            if *lock(&said) == "two words" {
                return;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        panic!("said {:?}", lock(&said));
    }
}
