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

/// The carrier a started process's standard input and output are, its standard error logged
/// line by line and its last line kept. On Windows, the first line a `wsl.exe` says there is
/// the pid in WSL of what it runs.
pub fn carried(kid: &Arc<Child>, said: &Said, wsl: bool) -> Result<Stream, String> {
    let (Some(mut stdin), Some(mut stdout), Some(stderr)) =
        (kid.take_stdin(), kid.take_stdout(), kid.take_stderr())
    else {
        return Err("the process could not be read".into());
    };
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
        while let Ok(n @ 1..) = stdout.read(&mut chunk) {
            if reading.block_on(to.write_all(&chunk[..n])).is_err() {
                break;
            }
        }
        // Ended once what it said last on its standard error is kept -- unless something it
        // left behind holds its standard error open.
        let _ = errors.recv_timeout(Duration::from_secs(1));
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

/// `hmz daemon connect --stdio` with the `hmz` given, in the environment given, from `home`.
#[cfg(unix)]
pub fn local(hmz: &std::path::Path, env: &crate::shell_env::Env) -> Command {
    let mut command = Command::new(hmz);
    command
        .args(["daemon", "connect", "--stdio"])
        .env_clear()
        .envs(env)
        .current_dir(crate::shell_env::home(env));
    piped(&mut command);
    command
}

/// What WSL runs for `stdio:wsl`: says its pid on its standard error, then becomes the `hmz` a
/// login shell finds, `~/.local/bin` included, connecting.
#[cfg(any(windows, test))]
const IN_WSL: &str = r#"echo $$ >&2; exec "${SHELL:-/bin/sh}" -lc "exec /bin/sh -c 'PATH=\"\$PATH:\$HOME/.local/bin\"; export PATH; exec hmz daemon connect --stdio'""#;

/// `wsl.exe [-d <distro>] --exec … hmz daemon connect --stdio`.
#[cfg(windows)]
pub fn wsl(distro: Option<&str>) -> Command {
    let mut command = crate::wsl::command_in(distro, "/bin/sh", None);
    command.args(["-c", IN_WSL]);
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
/// `sh`.
pub fn ssh(route: &Ssh, script: &str) -> Command {
    let mut command = Command::new("ssh");
    #[cfg(windows)]
    std::os::windows::process::CommandExt::creation_flags(
        &mut command,
        crate::wsl::CREATE_NO_WINDOW,
    );
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
/// `ssh`'s own, and what the host's says -- within `limit`.
fn ran(
    kids: &Kids,
    command: &mut Command,
    limit: Duration,
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
                return Err(format!("no answer in {} s", limit.as_secs()));
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
/// is `none`, `running` or `unknown`.
fn probed(kids: &Kids, route: &Ssh) -> Result<(String, String), String> {
    let (ok, lines) = ran(kids, &mut ssh(route, PROBE), PROBING, &|_| {})?;
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
/// the app's version as PyPI has it, None for a development build; `say` is told the state
/// and what was said last.
pub fn reach_ssh(
    kids: &Kids,
    route: &Ssh,
    wanted: Option<&str>,
    say: &dyn Fn(&'static str, &str),
) -> Result<Arc<Child>, String> {
    let host = &route.host;
    say("connecting", &format!("ssh {host}"));
    let (there, daemon) = probed(kids, route)?;
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
            let (ok, lines) = ran(kids, &mut ssh(route, &script), INSTALLING, &tell)?;
            if !ok {
                return Err(last(
                    &lines,
                    &format!("hmz {wanted} could not be installed."),
                ));
            }
            let (there, _) = probed(kids, route)?;
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
        assert_eq!(command.get_program(), "ssh");
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
        for script in [PROBE, THERE, &installing("1.2.3"), IN_WSL] {
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
        // What WSL's login shell is handed, run by sh here: hmz looked for on PATH, then in
        // ~/.local/bin.
        let home = tempfile::tempdir().unwrap();
        let bin = home.path().join(".local/bin");
        std::fs::create_dir_all(&bin).unwrap();
        let script = |path: &std::path::Path, text: &str| {
            use std::os::unix::fs::PermissionsExt;
            std::fs::write(path, text).unwrap();
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
        };
        script(&bin.join("hmz"), "#!/bin/sh\necho \"hmz $*\"\n");
        // A login shell that reads no profile, which would say what this machine's says.
        let shell = home.path().join("shell");
        script(
            &shell,
            "#!/bin/sh\n[ \"$1\" = -lc ] && exec /bin/sh -c \"$2\"\n",
        );
        let out = Command::new("/bin/sh")
            .args(["-c", IN_WSL])
            .env_clear()
            .env("HOME", home.path())
            .env("PATH", "/usr/bin:/bin")
            .env("SHELL", &shell)
            .output()
            .unwrap();
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            "hmz daemon connect --stdio\n"
        );
        let pid = String::from_utf8(out.stderr).unwrap();
        assert!(pid.trim().parse::<u32>().is_ok(), "{pid}");
    }

    #[cfg(unix)]
    #[tokio::test(flavor = "multi_thread")]
    async fn carries_bytes_through_a_process_both_ways() {
        let kids = Kids::new();
        let mut command = Command::new("/bin/cat");
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
