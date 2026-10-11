//! `hmz web`, as the app's child: finding the `hmz` installed here, starting it, reading where
//! it listens, telling when it stops on its own, and stopping it.

use std::ffi::OsStr;
use std::fmt;
use std::fs;
use std::io::{BufRead, BufReader};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{ChildStderr, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use shared_child::SharedChild;
use shared_child::unix::SharedChildExt;
use url::Url;

use crate::lock;
use crate::shell_env::Env;

/// Names the `hmz` to run, ahead of everything else: for development and tests.
const OVERRIDE: &str = "HUMANIZE_HMZ";

/// How long `hmz web` may take to say where it listens. A first start may build a cache.
const STARTING: Duration = Duration::from_secs(30);

/// How long `hmz web` may take to stop once interrupted, before it is killed.
const STOPPING: Duration = Duration::from_secs(3);

/// How much of what `hmz web` says on stderr is kept to show, from its end.
const KEPT: usize = 16 * 1024;

/// What the line naming the address starts with.
const SAID: &str = "hmz web: ";

/// Why `hmz web` did not start.
#[derive(Debug, PartialEq)]
pub enum Failure {
    /// No `hmz` here.
    Missing,
    /// An `hmz` older than this app, which does not take `web --attached`.
    Outdated,
    /// Anything else, as it said it.
    Failed(String),
}

/// Where `hmz web` listens. Its key lets a browser in, so it is shown only as its origin.
pub struct Address(Url);

impl Address {
    /// The address from the line `hmz web` prints: on the loopback, with a port.
    fn parse(line: &str) -> Option<Self> {
        let url = Url::parse(line.strip_prefix(SAID)?.trim()).ok()?;
        let loopback = url.scheme() == "http" && url.host_str() == Some("127.0.0.1");
        (loopback && url.port().is_some()).then_some(Self(url))
    }

    /// The whole address, key and all, for the window alone.
    pub fn url(&self) -> &Url {
        &self.0
    }

    pub fn port(&self) -> u16 {
        self.0.port().unwrap_or_default()
    }
}

impl fmt::Display for Address {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0.origin().ascii_serialization())
    }
}

impl fmt::Debug for Address {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Address({self})")
    }
}

/// `hmz web`, running.
pub struct Server {
    pub address: Address,
    child: SharedChild,
    /// Held open: `--attached` stops `hmz web` once it closes, so it goes however the app ends.
    _stdin: ChildStdin,
    stderr: Stderr,
    /// Whether `stop` was asked, so that the exit it brings is not taken for one of its own.
    stopping: AtomicBool,
}

impl Server {
    /// Blocks until `hmz web` exits, and says what it said last where it stopped on its own;
    /// None where `stop` stopped it.
    pub fn exited(&self) -> Option<String> {
        let status = self.child.wait().ok();
        if self.stopping.load(Ordering::SeqCst) {
            return None;
        }
        log::warn!("hmz web exited on its own: {}", how(status));
        Some(self.stderr.said(status))
    }

    /// Interrupts `hmz web`, as Ctrl+C would, and kills it if it has not stopped in time.
    pub fn stop(&self) {
        self.stopping.store(true, Ordering::SeqCst);
        log::info!("hmz web stopped: {}", how(ended(&self.child)));
    }
}

/// What `hmz web` says on stderr, as it says it: logged, and the end of it kept.
struct Stderr {
    kept: Arc<Mutex<String>>,
    closed: Mutex<Receiver<()>>,
}

impl Stderr {
    fn read(stderr: ChildStderr) -> Self {
        let kept = Arc::new(Mutex::new(String::new()));
        let (closing, closed) = mpsc::channel();
        let tail = kept.clone();
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                log::info!("stderr: {line}");
                keep(&mut lock(&tail), &line);
            }
            drop(closing);
        });
        Self {
            kept,
            closed: Mutex::new(closed),
        }
    }

    /// What it said, once it has all been read -- or soon, should something it started still
    /// hold the pipe -- or how it exited where it said nothing.
    fn said(&self, status: Option<ExitStatus>) -> String {
        let _ = lock(&self.closed).recv_timeout(Duration::from_secs(1));
        let said = lock(&self.kept).trim().to_owned();
        match (said.is_empty(), status) {
            (false, _) => said,
            (true, Some(status)) => format!("hmz web exited: {status}"),
            (true, None) => "hmz web exited".into(),
        }
    }
}

/// The `hmz` to run: the one `HUMANIZE_HMZ` names, or the first on `PATH`.
pub fn find(env: &Env) -> Option<PathBuf> {
    candidates(env).into_iter().find(|path| runnable(path))
}

fn candidates(env: &Env) -> Vec<PathBuf> {
    if let Some(named) = env
        .get(OsStr::new(OVERRIDE))
        .filter(|named| !named.is_empty())
    {
        return vec![named.into()];
    }
    env.get(OsStr::new("PATH"))
        .map(|path| {
            std::env::split_paths(path)
                .filter(|dir| dir.is_absolute())
                .map(|dir| dir.join("hmz"))
                .collect()
        })
        .unwrap_or_default()
}

fn runnable(path: &Path) -> bool {
    fs::metadata(path).is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
}

/// Starts `hmz web` on the port it had last, kept in `port_file` so that what its page keeps in
/// the browser, which is kept by origin, is there again; on any port where that one is taken.
pub fn start(env: &Env, home: &Path, port_file: &Path) -> Result<Server, Failure> {
    let hmz = find(env).ok_or(Failure::Missing)?;
    let last = fs::read_to_string(port_file)
        .ok()
        .and_then(|port| port.trim().parse().ok())
        .unwrap_or(0);
    log::info!("starting {} web on port {last}", hmz.display());
    let server = match spawn(&hmz, env, home, last) {
        Err(Early { code, stderr }) if retries(last, code, &stderr) => {
            log::info!("port {last} is taken; asking for any");
            spawn(&hmz, env, home, 0)
        }
        started => started,
    }
    .map_err(Early::failure)?;
    if server.address.port() != last {
        if let Some(dir) = port_file.parent() {
            let _ = fs::create_dir_all(dir);
        }
        if let Err(why) = fs::write(port_file, server.address.port().to_string()) {
            log::warn!("the port could not be kept: {why}");
        }
    }
    log::info!("hmz web listens at {}", server.address);
    Ok(server)
}

/// Whether a start that failed is worth one more on any port: the port asked for was taken.
fn retries(port: u16, code: Option<i32>, stderr: &str) -> bool {
    port != 0 && code == Some(1) && stderr.contains("cannot be served")
}

/// `hmz web` exiting before it said where it listens.
struct Early {
    code: Option<i32>,
    stderr: String,
}

impl Early {
    /// An `hmz` that refuses what it is asked -- `--attached`, or `web` itself -- is too old.
    fn failure(self) -> Failure {
        let refused = ["unrecognized arguments", "invalid choice"];
        if self.code == Some(2) && refused.iter().any(|said| self.stderr.contains(said)) {
            Failure::Outdated
        } else {
            Failure::Failed(self.stderr)
        }
    }
}

fn spawn(hmz: &Path, env: &Env, home: &Path, port: u16) -> Result<Server, Early> {
    let early = |stderr: String| Early { code: None, stderr };
    let mut command = Command::new(hmz);
    command
        .args(["web", "--no-open", "--attached", "--port"])
        .arg(port.to_string())
        .current_dir(home)
        .env_clear()
        .envs(env)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // The signals that stop it, as they are by default: a signal ignored is ignored in a child
    // too, and `hmz web` keeps one it was handed ignored -- so an app started where Ctrl+C is
    // ignored, as from a script's background job, would have Quit kill it rather than stop it.
    // SAFETY: `signal` is async-signal-safe, which is all that may run between fork and exec.
    unsafe {
        command.pre_exec(|| {
            for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP] {
                libc::signal(signal, libc::SIG_DFL);
            }
            Ok(())
        });
    }
    let child = SharedChild::spawn(&mut command)
        .map_err(|why| early(format!("{} could not be run: {why}", hmz.display())))?;
    let (Some(stdin), Some(stdout), Some(stderr)) =
        (child.take_stdin(), child.take_stdout(), child.take_stderr())
    else {
        ended(&child);
        return Err(early("hmz web could not be read".into()));
    };
    let stderr = Stderr::read(stderr);
    let (heard, said_where) = mpsc::channel();
    thread::spawn(move || {
        let mut lines = BufReader::new(stdout);
        let mut line = String::new();
        while lines.read_line(&mut line).is_ok_and(|n| n > 0) {
            if let Some(address) = Address::parse(&line) {
                let _ = heard.send(address);
                break;
            }
            line.clear();
        }
        // Drained to the end, so `hmz web` never blocks on a full pipe.
        let _ = std::io::copy(&mut lines.into_inner(), &mut std::io::sink());
    });
    match said_where.recv_timeout(STARTING) {
        Ok(address) => Ok(Server {
            address,
            child,
            _stdin: stdin,
            stderr,
            stopping: AtomicBool::new(false),
        }),
        Err(why) => {
            let status = match why {
                // Done with stdout is all but exited: what it exits with is its own.
                RecvTimeoutError::Disconnected => child
                    .wait_timeout(STOPPING)
                    .ok()
                    .flatten()
                    .or_else(|| ended(&child)),
                RecvTimeoutError::Timeout => ended(&child),
            };
            let mut said = stderr.said(status);
            if why == RecvTimeoutError::Timeout {
                said = format!(
                    "hmz web did not say where it listens within {} s\n{said}",
                    STARTING.as_secs()
                );
            }
            Err(Early {
                code: status.and_then(|status| status.code()),
                stderr: said,
            })
        }
    }
}

/// Interrupts a child, as Ctrl+C would, and kills it if it has not stopped in time. Reaped
/// either way.
fn ended(child: &SharedChild) -> Option<ExitStatus> {
    let _ = child.send_signal(libc::SIGINT);
    if let Ok(Some(status)) = child.wait_timeout(STOPPING) {
        return Some(status);
    }
    log::warn!(
        "hmz web did not stop in {} s; killing it",
        STOPPING.as_secs()
    );
    let _ = child.kill();
    child.wait().ok()
}

/// How a child exited, for the log.
fn how(status: Option<ExitStatus>) -> String {
    status.map_or_else(|| "unknown".into(), |status| status.to_string())
}

/// Keeps a line of stderr, and no more than the last `KEPT` bytes of it all.
fn keep(kept: &mut String, line: &str) {
    kept.push_str(line);
    kept.push('\n');
    if kept.len() > KEPT {
        let mut cut = kept.len() - KEPT;
        while !kept.is_char_boundary(cut) {
            cut += 1;
        }
        kept.drain(..cut);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Once;
    use std::time::Instant;

    const KEY: &str = "s3cret";

    /// Every line logged in this process, to tell that the key is in none of them.
    static LOGGED: Mutex<Vec<String>> = Mutex::new(Vec::new());

    struct Kept;

    impl log::Log for Kept {
        fn enabled(&self, _: &log::Metadata) -> bool {
            true
        }
        fn log(&self, record: &log::Record) {
            lock(&LOGGED).push(record.args().to_string());
        }
        fn flush(&self) {}
    }

    fn logging() {
        static ONCE: Once = Once::new();
        ONCE.call_once(|| {
            let _ = log::set_logger(&Kept);
            log::set_max_level(log::LevelFilter::Trace);
        });
    }

    /// A stand-in for `hmz`, doing what `$FAKE` says, in a home of its own.
    struct Fake {
        home: tempfile::TempDir,
        env: Env,
    }

    impl Fake {
        fn new(mode: &str) -> Self {
            let home = tempfile::tempdir().unwrap();
            let hmz = home.path().join("hmz");
            fs::write(&hmz, FAKE).unwrap();
            fs::set_permissions(&hmz, fs::Permissions::from_mode(0o755)).unwrap();
            let env = Env::from([
                ("PATH".into(), "/usr/bin:/bin".into()),
                ("HOME".into(), home.path().into()),
                (OVERRIDE.into(), hmz.into()),
                ("FAKE".into(), mode.into()),
            ]);
            Self { home, env }
        }

        fn port_file(&self) -> PathBuf {
            self.home.path().join("data/port")
        }

        fn read(&self, name: &str) -> String {
            fs::read_to_string(self.home.path().join(name)).unwrap()
        }

        fn start(&self) -> Result<Server, Failure> {
            logging();
            start(&self.env, self.home.path(), &self.port_file())
        }
    }

    /// `hmz web --no-open --attached --port <port>`, as each `$FAKE` has it behave.
    const FAKE: &str = r#"#!/bin/sh
pwd > "$HOME/cwd"
echo "$@" > "$HOME/args"
port="$5"
case "$FAKE" in
  old)
    echo "usage: hmz web [-h] [--port PORT] [--no-open]" >&2
    echo "hmz web: error: unrecognized arguments: --attached" >&2
    exit 2 ;;
  broken)
    echo "hmz: these runs are held by an older humanize" >&2
    exit 1 ;;
  taken)
    if [ "$port" != 0 ]; then
      echo "hmz: the web interface cannot be served: [Errno 48] Address already in use" >&2
      exit 1
    fi ;;
esac
[ "$port" = 0 ] && port=4321
echo "hmz web: http://127.0.0.1:$port/?key=s3cret"
if [ "$FAKE" = crash ]; then
  sleep 0.2
  echo "Traceback: boom" >&2
  exit 3
fi
# Stopped by Ctrl+C alone, cleanly -- which a shell handed SIGINT ignored cannot trap.
if [ "$FAKE" = trapping ]; then
  trap 'exit 0' INT
  while :; do sleep 0.05; done
fi
# --attached: until stdin closes.
exec cat > /dev/null
"#;

    fn gone(server: &Server) -> bool {
        (unsafe { libc::kill(server.child.id() as libc::pid_t, 0) }) != 0
    }

    #[test]
    fn reads_the_address_and_never_shows_its_key() {
        let address = Address::parse("hmz web: http://127.0.0.1:8765/?key=s3cret\n").unwrap();
        assert_eq!(address.port(), 8765);
        assert_eq!(address.url().as_str(), "http://127.0.0.1:8765/?key=s3cret");
        assert_eq!(address.to_string(), "http://127.0.0.1:8765");
        assert!(!format!("{address:?}").contains(KEY));
        for line in [
            "http://127.0.0.1:8765/?key=s3cret",
            "hmz web: https://127.0.0.1:8765/",
            "hmz web: http://example.com:8765/",
            "hmz web: http://127.0.0.1/",
            "hmz web: not an address",
        ] {
            assert!(Address::parse(line).is_none(), "{line}");
        }
    }

    #[test]
    fn looks_where_it_is_told_then_along_path() {
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b".into()),
            (OVERRIDE.into(), "/named/hmz".into()),
        ]);
        assert_eq!(candidates(&env), [PathBuf::from("/named/hmz")]);
        let env = Env::from([
            ("PATH".into(), "/a:relative:/b".into()),
            (OVERRIDE.into(), "".into()),
        ]);
        assert_eq!(
            candidates(&env),
            [PathBuf::from("/a/hmz"), PathBuf::from("/b/hmz")]
        );
        assert!(candidates(&Env::new()).is_empty());
    }

    #[test]
    fn finds_the_first_runnable_hmz() {
        let dirs: Vec<_> = (0..3).map(|_| tempfile::tempdir().unwrap()).collect();
        fs::write(dirs[0].path().join("hmz"), "").unwrap();
        for dir in &dirs[1..] {
            let hmz = dir.path().join("hmz");
            fs::write(&hmz, "").unwrap();
            fs::set_permissions(&hmz, fs::Permissions::from_mode(0o755)).unwrap();
        }
        let path = std::env::join_paths(dirs.iter().map(|dir| dir.path())).unwrap();
        let env = Env::from([("PATH".into(), path)]);
        assert_eq!(find(&env), Some(dirs[1].path().join("hmz")));
    }

    #[test]
    fn retries_on_any_port_only_where_its_own_was_taken() {
        let taken = "hmz: the web interface cannot be served: [Errno 48] Address already in use";
        assert!(retries(8765, Some(1), taken));
        assert!(!retries(0, Some(1), taken));
        assert!(!retries(
            8765,
            Some(1),
            "hmz: these runs are held by an older humanize"
        ));
        assert!(!retries(8765, Some(2), taken));
    }

    #[test]
    fn keeps_the_end_of_what_it_said() {
        let mut kept = String::new();
        for _ in 0..KEPT {
            keep(&mut kept, "é");
        }
        assert!(kept.len() <= KEPT);
        assert!(kept.ends_with("é\n"));
    }

    #[test]
    fn starts_in_home_remembers_its_port_and_stops() {
        let fake = Fake::new("ok");
        let server = Arc::new(fake.start().unwrap());
        assert_eq!(server.address.port(), 4321);
        assert_eq!(fs::read_to_string(fake.port_file()).unwrap(), "4321");
        assert_eq!(
            Path::new(fake.read("cwd").trim()).canonicalize().unwrap(),
            fake.home.path().canonicalize().unwrap()
        );
        assert_eq!(fake.read("args"), "web --no-open --attached --port 0\n");
        let watched = server.clone();
        let watcher = thread::spawn(move || watched.exited());
        let began = Instant::now();
        server.stop();
        assert!(began.elapsed() < STOPPING);
        assert!(gone(&server));
        assert_eq!(watcher.join().unwrap(), None);

        // Again, on the port it had.
        let server = fake.start().unwrap();
        assert_eq!(fake.read("args"), "web --no-open --attached --port 4321\n");
        server.stop();
        assert!(!lock(&LOGGED).iter().any(|line| line.contains(KEY)));
    }

    #[test]
    fn takes_any_port_where_its_own_is_taken() {
        let fake = Fake::new("taken");
        fs::create_dir_all(fake.home.path().join("data")).unwrap();
        fs::write(fake.port_file(), "5555").unwrap();
        let server = fake.start().unwrap();
        assert_eq!(server.address.port(), 4321);
        assert_eq!(fs::read_to_string(fake.port_file()).unwrap(), "4321");
        server.stop();
    }

    #[test]
    fn says_why_it_did_not_start() {
        let fake = Fake::new("ok");
        let mut env = fake.env.clone();
        env.insert(OVERRIDE.into(), "/nonexistent/hmz".into());
        let missing = start(&env, fake.home.path(), &fake.port_file());
        assert_eq!(missing.err(), Some(Failure::Missing));
        assert_eq!(Fake::new("old").start().err(), Some(Failure::Outdated));
        let older = Early {
            code: Some(2),
            stderr: "hmz: error: argument command: invalid choice: 'web'".into(),
        };
        assert_eq!(older.failure(), Failure::Outdated);
        assert_eq!(
            Fake::new("broken").start().err(),
            Some(Failure::Failed(
                "hmz: these runs are held by an older humanize".into()
            ))
        );
    }

    #[test]
    fn interrupts_it_where_the_app_was_started_ignoring_ctrl_c() {
        // As from a script's background job, which hands on SIGINT ignored.
        let was = unsafe { libc::signal(libc::SIGINT, libc::SIG_IGN) };
        let server = Fake::new("trapping").start();
        unsafe { libc::signal(libc::SIGINT, was) };
        let server = server.unwrap();
        let status = ended(&server.child).unwrap();
        assert_eq!(status.code(), Some(0), "{status}");
    }

    #[test]
    fn tells_when_it_stops_on_its_own() {
        let server = Fake::new("crash").start().unwrap();
        let said = server.exited().unwrap();
        assert!(said.contains("Traceback: boom"), "{said}");
        assert!(gone(&server));
        // Nothing is left to stop.
        server.stop();
    }
}
